/** 
* @file ur5_controller_lib.h 
* @brief Header file for the UR5 Controller class and library
*
* @author Samuele Pozzani
*
* @date 18/12/2022
*/

#ifndef __UR5_CONTROLLER_H__
#define __UR5_CONTROLLER_H__

#include "kinematics_lib/ur5_kinematics.h"
#include "ros/ros.h"
#include <sensor_msgs/JointState.h>

/**
 * @brief The UR5 Controller class implements the high level functions for the movement and control of UR5
 * @class UR5Controller
 */
class UR5Controller
{
private:
    ros::NodeHandle node;
    ros::Rate loop_rate;
    ros::Publisher joint_state_pub;
    ros::Publisher gripper_state_pub;
    ros::Subscriber joint_state_sub;

    double settling_time;
    double loop_frequency;
    double joints_error;

    std::string joint_names[9] = {"shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint",
                                  "wrist_1_joint", "wrist_2_joint", "wrist_3_joint",
                                  "hand_1_joint", "hand_2_joint", "hand_3_joint"};

    JointStateVector current_joints;
    GripperStateVector current_gripper;
    bool is_real_robot = false;
    bool using_soft_gripper = false;
    bool is_simulating_gripper = false;

    int gripper_diameter;

    /**
     * Callback function, listen to /ur5/joint_states topic and update current_pos
     * 
     * @param msg The data received from the topic
     */
    void joint_state_callback(const sensor_msgs::JointState::ConstPtr &msg);

    /**
     * Convert the JointStateVector desired_pos to a Float64MultiArray,
     * then send the array to ros topic defined by the joint_state_pub publisher
     * 
     * @param desired_joints The desired configuration to be sent to the topic 
     */
    void send_joint_state(const JointStateVector &desired_joints) const;

    /**
     * Send desired diameter to /ur5/gripper_controller/command to open/close the gripper
     * 
     * @param diameter The value of the gripper aperture
     */
    void send_gripper_state(int diameter) const;

    /**
     * Compute joint values by following consecutive approximations.
     * The velocity of the end effector remains constant.
     * Use this function iteratively to send joint states to the robot and avoid steps.
     * Use init_filters function before starting to use this filter.
     * 
     * @param final_joints The desired joints configuration
     * @return The filtered configuration
     */
    JointStateVector linear_filter(const JointStateVector &final_joints);

    /**
     * Init values of the linear filter 
     */
    void init_filters(void);

    /**
     * Compute difference between the two vectors, by normalizing the angles first.
     * Eg. -PI/2 will be equal to 3*PI/2
     * 
     * @param first_vector The first joints configuration
     * @param second_vecotr The second joints configuration
     * @return The norm of the difference between first and second vectors
     */
    double compute_error(const JointStateVector &first_vector, const JointStateVector &second_vector) const;

    /**
     * For every joint configuration: 
     * 1. Compute direct kinematics and check if the posititon collides with the workbanch
     * 2. Compute jacobian, its determinant and the minimum singular value to avoid singularities
     * 
     * @param path Pointer to the vector of n * 6 elements, it represents the n configurations of the joints during the trajectory
     * @param n The number of configurations of the joints during the trajectory
     * @return true if path is valid, false if some constraints are not met
     */
    bool validate_path(double *path, int n) const;

public:
    /**
     * Constructor. Initialize ros publishers and subscribers.
     * 
     * @param loop_frequency Specifies the rate of received and sent instruction in a movement loop.
     * @param joints_error Acceptable error between desired position and effective position at the end of a movement operation. Higher value => less precision.
     * @param settling_time Required time to complete a movement operation. Higher value => higher speed.
     */
    UR5Controller(double loop_frequency, double joints_error, double settling_time);

    /**
     * Move end effector to desired position (pos) and rotation (rot) by following a path computed by the kinematics libray
     * 
     * @param pos Final cartesian position of the end effector
     * @param rot Final rotation of the end effector
     * @param n Number of intermediate points
     * @return true if path was valid and movement succeded
     * 
     * This function follows the procedure:
     * 1. Read the /ur5/joint_states topic and get the initial configuration 
     * 2. Compute complete inverse kinematics to find all the possibile final configurations
     * 3. Compute the path of for every ik solution
     * 4. Compute direct kinematics on every configuration inside the path and check position and singularity constraints
     * 5. If the path is acceptable, follow it 
     */
    bool move_to(const Coordinates &pos, const RotationMatrix &rot, int n);

    /**
     * Open and close the gripper at the selected diameter
     * 
     * @param diameter The aperture of the gripper
     */
    void set_gripper(int diameter);

    /**
     * Save current joint state vector in the parameter joints
     * 
     * @return The current joint configuration
     */
    JointStateVector get_joint_states(void) const;
};

/**
 * Sort the 8 inverse kinematics results in ascending order by the norm of the difference between the
 * initial joints and the solution of the IK.
 * 
 * @param ik_result The 8x6 matrix containing the 8 results of the IK
 * @param initial_joints The joint vector that is compared to the IK results
 * @return A dynamically allocated vector containing the sorted indexes of the IK results    
*/
int *sort_ik_result(const Eigen::Matrix<double, 8, 6> &ik_result, const JointStateVector &initial_joints);

#endif