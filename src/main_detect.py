#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rospy
import numpy as np
import tf
import cv2
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image
from ultralytics import YOLO
import torch
from sensor_msgs import point_cloud2 as pc2
from sensor_msgs.msg import Image, PointCloud2
from detector_2d.msg import DicBoxes, CoordBoxes
import processing as pr
import time
import traceback


class Detector:
    def __init__(self):
        self._global_frame = 'zed2_left_camera_frame'

        image_topic = rospy.get_param('~image_topic')
        point_cloud_topic = rospy.get_param('~point_cloud_topic', None)

        self._global_frame = rospy.get_param('~global_frame', None)
        self._tf_prefix = rospy.get_param('~tf_prefix', rospy.get_name())
        self.yolo = YOLO("/home/robofei/Workspace/catkin_ws/src/vision_system/detector_2d/src/best.pt")

        self._tf_listener = tf.TransformListener()
        self._current_image = None
        self._current_pc = None
        (robot_trans, robot_rot) = self._tf_listener.lookupTransform('/zed2_camera_center', '/base', rospy.Time(0))

        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Create detector
        self._bridge = CvBridge()

        # Image and point cloud subscribers and variables that will hold their values
        self._image_sub = rospy.Subscriber(image_topic, Image, self.image_callback)

        # Publisher for frames with detected objects
        self._imagepub = rospy.Publisher('~objects_label', Image, queue_size=10)
        self._boxespub = rospy.Publisher('~boxes_coordinates', DicBoxes, queue_size=10)

        if point_cloud_topic is not None:
            rospy.Subscriber(point_cloud_topic, PointCloud2, self.pc_callback)
        else:
            rospy.loginfo('No point cloud information available. Objects will not be placed in the scene.')

        self._tfpub = tf.TransformBroadcaster()
        rospy.loginfo('Ready to detect!')

    def image_callback(self, image):
        """Image callback"""
        # Store value on a private attribute
        self._current_image = image

    def pc_callback(self, pc):
        """Point cloud callback"""
        # Store value on a private attribute
        self._current_pc = pc

    def run(self):
        # Run while ROS runs
        frame_rate = 5
        prev = 0
        while not rospy.is_shutdown():
            time_elapsed = time.time() - prev
            if time_elapsed > 1. / frame_rate:
                prev = time.time()
                # Only run if there's an image present
                if self._current_image is not None:
                    try:
                        # Search image
                        small_frame = self._bridge.imgmsg_to_cv2(self._current_image, desired_encoding='bgr8')

                        if self._global_frame is not None:
                            (robot_trans, robot_rot) = self._tf_listener.lookupTransform('/zed2_camera_center', '/base', rospy.Time(0))
                            (trans, _) = self._tf_listener.lookupTransform('/' + self._global_frame, '/zed2_camera_center', rospy.Time(0))
                        # Load model
                        results = self.yolo.predict(source=small_frame, conf=0.5, device=0)

                        # Boxes to msg
                        boxes = results[0].boxes
                        rospy.loginfo("boxes: %s", boxes)
                        rospy.loginfo("box classes: %s", boxes.cls)
                        for i, c in enumerate(boxes.cls):
                            arr = boxes[i].xywh[0]
                            aux = CoordBoxes()
                            obj_class = self.yolo.names[int(c)]
                            aux.class_.data = self.yolo.names[int(c)]
                            aux.x.data = int(arr[0].item())
                            aux.y.data = int(arr[1].item())
                            aux.w.data = int(arr[2].item())
                            aux.h.data = int(arr[3].item())

                            # Publish tf
                            publish_tf = False
                            if self._current_pc is None:
                                rospy.loginfo('No point cloud')
                            else:
                                x_center = int(boxes[i].xywh[0][0])
                                y_center = int(boxes[i].xywh[0][1])

                                pc_list = list(
                                    pc2.read_points(self._current_pc,
                                                    skip_nans=True,
                                                    field_names=('x', 'y', 'z'),
                                                    uvs=[(x_center, y_center)]))

                                if len(pc_list) > 0:
                                    publish_tf = True
                                    tf_id = obj_class + '_' + str(c)
                                    point_z, point_x, point_y = pc_list[0]

                                # If the user passes a tf prefix, we append it to the object tf name here
                                if self._tf_prefix is not None:
                                    tf_id = self._tf_prefix + '/' + str(self.yolo.names[int(c)]) + str(i)
                                    aux.id.data = tf_id

                            if publish_tf:
                                # Object tf (x, y, z) must be passed as (z, -x, -y)
                                object_tf = [point_z, point_x, point_y]
                                frame = 'zed2_camera_center'

                                # Translate the tf in regard to the fixed frame
                                if self._global_frame is not None:
                                    object_tf = np.array(trans) + object_tf
                                    frame = self._global_frame

                                if object_tf is not None:
                                    self._tfpub.sendTransform((object_tf),
                                                              tf.transformations.quaternion_from_euler(0, 0, 0),
                                                              rospy.Time.now(),
                                                              tf_id,
                                                              frame)

                        rospy.loginfo(self.yolo.names)

                        # Plot bbox
                        small_frame = pr.plot_bboxes(small_frame, results[0].boxes.boxes, self.yolo.names, conf=0.5)

                        # Publisher
                        self._imagepub.publish(self._bridge.cv2_to_imgmsg(small_frame, 'rgb8'))

                    except Exception:
                        traceback.print_exc()

if __name__ == '__main__':
    rospy.init_node('detector_2d', log_level=rospy.INFO)
    try:
        Detector().run()
    except KeyboardInterrupt:
        rospy.loginfo('Shutting down')
