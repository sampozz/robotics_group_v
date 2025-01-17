#!/usr/bin/env python3

import rospy
import cv2
import torch
import torch.backends.cudnn as cudnn
import numpy as np
from cv_bridge import CvBridge
from pathlib import Path
import os
import sys
from rostopic import get_topic_type

from sensor_msgs.msg import Image, CompressedImage
from robotic_vision.msg import BoundingBox, BoundingBoxes
from nav_msgs.msg import Odometry
from robotic_vision.srv import Ping, PingResponse


# add yolov5 submodule to path
FILE = Path(__file__).resolve()
ROOT = FILE.parents[0] / "yolov5"
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH
ROOT = Path(os.path.relpath(ROOT, Path.cwd()))  # relative path

# import from yolov5 submodules
from models.common import DetectMultiBackend
from utils.general import (
    check_img_size,
    check_requirements,
    non_max_suppression,
    scale_coords
)
from utils.plots import Annotator, colors
from utils.torch_utils import select_device
from utils.augmentations import letterbox


@torch.no_grad()
class Yolov5Detector:

    def __init__(self, namespace="shelfino"):

        self.namespace = namespace
        self.conf_thres = rospy.get_param("~confidence_threshold")
        self.iou_thres = rospy.get_param("~iou_threshold")
        self.agnostic_nms = rospy.get_param("~agnostic_nms")
        self.max_det = rospy.get_param("~maximum_detections")
        self.classes = rospy.get_param("~classes", None)
        self.line_thickness = rospy.get_param("~line_thickness")
        self.view_image = rospy.get_param(f"~{namespace}/view_image")
        # Initialize weights 
        weights = rospy.get_param("~weights")
        # Initialize model
        self.device = select_device(str(rospy.get_param("~device","")))
        self.model = DetectMultiBackend(weights, device=self.device, dnn=rospy.get_param("~dnn"), data=rospy.get_param("~data"))
        self.stride, self.names, self.pt, self.jit, self.onnx, self.engine = (
            self.model.stride,
            self.model.names,
            self.model.pt,
            self.model.jit,
            self.model.onnx,
            self.model.engine,
        )

        # Setting inference size
        self.img_size = [rospy.get_param("~inference_size_w", 640), rospy.get_param("~inference_size_h",480)]
        self.img_size = check_img_size(self.img_size, s=self.stride)

        # Half
        self.half = rospy.get_param("~half", False)
        self.half &= (
            self.pt or self.jit or self.onnx or self.engine
        ) and self.device.type != "cpu"  # FP16 supported on limited backends with CUDA
        if self.pt or self.jit:
            self.model.model.half() if self.half else self.model.model.float()
        bs = 1  # batch_size
        cudnn.benchmark = True  # set True to speed up constant image size inference
        self.model.warmup(imgsz=(1 if self.pt else bs, 3, *self.img_size), half=self.half)  # warmup        
        
        # Initialize subscriber to Image/CompressedImage topic
        input_image_type, input_image_topic, _ = get_topic_type(rospy.get_param(f"~{namespace}/input_image_topic"), blocking = True)
        self.compressed_input = input_image_type == "sensor_msgs/CompressedImage"

        if self.compressed_input:
            self.image_sub = rospy.Subscriber(
                input_image_topic, CompressedImage, self.color_callback, queue_size=1
            )
        else:
            self.image_sub = rospy.Subscriber(
                input_image_topic, Image, self.color_callback, queue_size=1
            )

        if namespace == "shelfino":
            # Initialize subscriber to depth camera
            _, input_depth_topic, _ = get_topic_type(rospy.get_param(f"~{namespace}/input_depth_topic"), blocking = True)
            self.depth_sub = rospy.Subscriber(
                input_depth_topic, Image, self.depth_callback, queue_size=1
            )

            # Initialize subscriber to schelfino odometry
            self.blacklist = []
            self.odom_position = [0, 0]
            self.odometry_sub = rospy.Subscriber(
                "/shelfino2/odom", Odometry, self.odometry_callback, queue_size=100
            )

            # Initialize service for blacklisting blocks
            self.blacklist_srv = rospy.Service(f'{namespace}/yolo/stop', Ping, self.blacklist_service)

        # Initialize prediction publisher
        self.pred_pub = rospy.Publisher(
            rospy.get_param(f"~{namespace}/output_topic"), BoundingBoxes, queue_size=10
        )
        # Initialize image publisher
        self.publish_image = rospy.get_param("~publish_image")
        if self.publish_image:
            self.image_pub = rospy.Publisher(
                rospy.get_param("~output_image_topic"), Image, queue_size=10
            )
        
        # Initialize CV_Bridge
        self.bridge = CvBridge()


    def odometry_callback(self, data):
        self.odom_position[0] = data.pose.pose.position.x 
        self.odom_position[1] = data.pose.pose.position.y 

    
    def blacklist_service(self, req):
        self.blacklist.append((self.odom_position[0], self.odom_position[1]))
        return PingResponse()


    def depth_callback(self, data):
        """ Save depth image, it has to be used only if block is identified """
        self.depth_image = self.bridge.imgmsg_to_cv2(data, "32FC1")


    def color_callback(self, data):
        """adapted from yolov5/detect.py"""
        # print(data.header)
        if self.compressed_input:
            im = self.bridge.compressed_imgmsg_to_cv2(data, desired_encoding="bgr8")
        else:
            im = self.bridge.imgmsg_to_cv2(data, desired_encoding="bgr8")
        
        im, im0 = self.preprocess(im)
        # print(im.shape)
        # print(img0.shape)
        # print(img.shape)

        # Run inference
        im = torch.from_numpy(im).to(self.device) 
        im = im.half() if self.half else im.float()
        im /= 255
        if len(im.shape) == 3:
            im = im[None]

        pred = self.model(im, augment=False, visualize=False)
        pred = non_max_suppression(
            pred, self.conf_thres, self.iou_thres, self.classes, self.agnostic_nms, max_det=self.max_det
        )

        ### To-do move pred to CPU and fill BoundingBox messages
        
        # Process predictions 
        det = pred[0].cpu().numpy()

        bounding_boxes = BoundingBoxes()
        bounding_boxes.n = 0
        bounding_boxes.header = data.header
        bounding_boxes.image_header = data.header
        
        annotator = Annotator(im0, line_width=self.line_thickness, example=str(self.names))
        if len(det):
            # Rescale boxes from img_size to im0 size
            det[:, :4] = scale_coords(im.shape[2:], det[:, :4], im0.shape).round()

            # Write results
            for *xyxy, conf, cls in reversed(det):
                bounding_box = BoundingBox()
                c = int(cls)
                # Fill in bounding box message
                bounding_box.Class = self.names[c]
                bounding_box.class_n = c
                bounding_box.probability = conf 
                bounding_box.xmin = int(xyxy[0])
                bounding_box.ymin = int(xyxy[1])
                bounding_box.xmax = int(xyxy[2])
                bounding_box.ymax = int(xyxy[3])

                bounding_boxes.bounding_boxes.append(bounding_box)

                # Annotate the image
                if self.publish_image or self.view_image:  # Add bbox to image
                      # integer class
                    label = f"{self.names[c]} {conf:.2f}"
                    annotator.box_label(xyxy, label, color=colors(c, True))       

                ### POPULATE THE DETECTION MESSAGE HERE
                if self.namespace == "shelfino":
                    # Compute distance from depth image
                    depth_sum = 0
                    for i in range(bounding_box.xmin, bounding_box.xmax):
                        for j in range(bounding_box.ymin, bounding_box.ymax):
                            depth_sum += self.depth_image[j][i]
                    bounding_box.distance = depth_sum / ((bounding_box.xmax - bounding_box.xmin) * (bounding_box.ymax - bounding_box.ymin))

                    # Check if block is blacklisted
                    bounding_box.is_blacklisted = False
                    for tuple in self.blacklist:
                        if abs(self.odom_position[0] - tuple[0]) < 0.15 and abs(self.odom_position[1] - tuple[1]) < 0.15:
                            bounding_box.is_blacklisted = True

            # Stream results
            bounding_boxes.n = len(bounding_boxes.bounding_boxes)
            im0 = annotator.result()

        # Publish prediction
        self.pred_pub.publish(bounding_boxes)

        # Publish & visualize images
        if self.view_image:
            cv2.imshow(self.namespace, im0)
            cv2.waitKey(1)  # 1 millisecond
        if self.publish_image:
            self.image_pub.publish(self.bridge.cv2_to_imgmsg(im0, "bgr8"))
        

    def preprocess(self, img):
        """
        Adapted from yolov5/utils/datasets.py LoadStreams class
        """
        img0 = img.copy()
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        img = np.array([letterbox(img, self.img_size, stride=self.stride, auto=self.pt)[0]])
        
        # Convert
        img = img[..., ::-1].transpose((0, 3, 1, 2))  # BGR to RGB, BHWC to BCHW
        
        img = np.ascontiguousarray(img)

        return img, img0 


if __name__ == "__main__":

    check_requirements(exclude=("tensorboard", "thop"))
    
    rospy.init_node("yolov5", anonymous=True)

    namespace = rospy.get_param(f"~namespace")
    shelfino_detector = Yolov5Detector(namespace=namespace)

    rospy.spin()
