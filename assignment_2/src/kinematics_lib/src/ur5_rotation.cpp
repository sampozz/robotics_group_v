#include "kinematics_lib/ur5_kinematics.h"
#include "kinematics_lib/shelfino_kinematics.h"

/* Public functions */

void euler_to_rot(double roll, double pitch, double yaw, RotationMatrix &rot)
{
    RotationMatrix x_rot;
    RotationMatrix y_rot;
    RotationMatrix z_rot;

    x_rot << 1, 0, 0,
        0, cos(yaw), -sin(yaw),
        0, sin(yaw), cos(yaw);

    y_rot << cos(pitch), 0, sin(pitch),
        0, 1, 0,
        -sin(pitch), 0, cos(pitch);

    z_rot << cos(roll), -sin(roll), 0,
        sin(roll), cos(roll), 0,
        0, 0, 1;

    rot = z_rot * y_rot * x_rot;
}

double quaternion_to_yaw(double qx, double qy, double qz, double qw)
{
    // yaw (z-axis rotation)
    double siny_cosp = 2 * (qw * qz + qx * qy);
    double cosy_cosp = 1 - 2 * (qy * qy + qz * qz);
    return std::atan2(siny_cosp, cosy_cosp);
}

double norm_angle(double angle)
{
    if (angle == 0)
        return 0;
    if (angle > 0)
        angle = fmod(angle, 2 * M_PI);
    else
        angle = 2 * M_PI - fmod(-angle, 2 * M_PI);
    return angle;
}