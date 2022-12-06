#include "ros/ros.h"
#include "ur5_controller/ur5_controller_lib.h"
#include "ur5_controller/MoveTo.h"
#include "ur5_controller/SetGripper.h"

UR5Controller *controller_ptr = nullptr;

bool move_to(ur5_controller::MoveTo::Request &req, ur5_controller::MoveTo::Response &res)
{
    Coordinates pos;
    RotationMatrix rot;
    pos << req.pos.x, req.pos.y, req.pos.z;
    euler_to_rot(req.rot.roll, req.rot.pitch, req.rot.yaw, rot);

    res.status = controller_ptr->ur5_follow_path(pos, rot, 20);

    return true;
}


bool set_gripper(ur5_controller::SetGripper::Request &req, ur5_controller::SetGripper::Response &res)
{
    controller_ptr->ur5_set_gripper(req.diameter);

    return true;
}


int main(int argc, char **argv)
{
    // ROS Node initialization
    ros::init(argc, argv, "ur5_controller_node");
    ros::NodeHandle controller_node;

    UR5Controller controller(1000.0, 0.005, 10.0);
    controller_ptr = &controller;

    ros::ServiceServer move_service = controller_node.advertiseService("move_to", move_to);
    ros::ServiceServer gripper_service = controller_node.advertiseService("set_gripper", set_gripper);
    ros::spin();

    return 0;
}
