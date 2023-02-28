#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rospy
import numpy as np
import tf

from calendar import c
from pyexpat import model

from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs import point_cloud2 as pc2
from sensor_msgs.msg import Image, PointCloud2
#from regex import E, F
import rospy
from sensor_msgs.msg import Image
import cv2
from cv_bridge import CvBridge, CvBridgeError
from hera_face.srv import face_list
import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.yolo.v8.detect.predict import DetectionPredictor
#from PIL import Image

class Detector:

    def __init__(self):
        image_topic = '~/zed2/zed_node/left_raw/image_raw_color'
        point_cloud_topic = '/zed2/zed_node/point_cloud/cloud_registered'

        self._global_frame = 'camera'
        self._frame = 'camera_depth_frame'
        self._tf_listener = tf.TransformListener()
        # create detector
        self._bridge = CvBridge()

        # image and point cloud subscribers
        # and variables that will hold their values
        rospy.Subscriber(image_topic, Image, self.image_callback)

        if point_cloud_topic is not None:
            rospy.Subscriber(point_cloud_topic, PointCloud2, self.pc_callback)
        else:
            rospy.loginfo(
                'No point cloud information available. Objects will not be placed in the scene.')

        self._current_image = None
        self._current_pc = None

        # publisher for frames with detected objects
        self._imagepub = rospy.Publisher('~labeled_persons', Image, queue_size=10)

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
        # run while ROS runs
        while not rospy.is_shutdown():
            # only run if there's an image present
            if self._current_image is not None:
                try:
                    # if the user passes a fixed frame, we'll ask for transformation
                    # vectors from the camera link to the fixed frame
                    # if self._global_frame is not None:
                    #     (trans, _) = self._tf_listener.lookupTransform('/' + self._global_frame,
                    #                                                    '/' + self._frame, rospy.Time(0))
                    small_frame = self._bridge.imgmsg_to_cv2(self._current_image, desired_encoding='bgr8')
                    # small_frame = self._bridge.imgmsg_to_cv2(, 'rgb8')
                    yolo = YOLO("yolov8n.pt")
                    results = yolo.predict(source=small_frame, conf=0.8)
                    boxes = results[0].boxes
                    #plot_bboxes(small_frame, boxes.boxes, score=False, conf=0.5)

                    #marked_image = np.squeeze(boxes)
                    for r in results:
                        for i in range(len(boxes)):
                            box = boxes[i]
                            dim = box.xyxy[0].to(torch.int32)
                            cv2.rectangle(small_frame, (dim[0].item(), dim[1].item()), (dim[2].item(), dim[3].item()), (0,255,0), 2)
                            # publish the image with the bounding boxes
                            self._imagepub.publish(self._bridge.cv2_to_imgmsg(small_frame, 'rgb8'))
                            for c in r.boxes.cls:
                                publish_tf = False
                                if self._current_pc is None:
                                    rospy.loginfo(
                                        'No point cloud information available to track current object in scene')

                            #     # if there is point cloud data, we'll try to place a tf
                            #     # in the object's location
                            #     else:
                            #         y_center = round((dim[1].item() + dim[3].item()) / 2)
                            #         x_center = round((dim[0].item() + dim[2].item()) / 2)
                            #         # this function gives us a generator of points.
                            #         # we ask for a single point in the center of our object.
                            #         try:
                            #             pc_list = list(
                            #                 pc2.read_points(self._current_pc,
                            #                                 skip_nans=True,
                            #                                 field_names=('x', 'y', 'z'),
                            #                                 uvs=[(x_center, y_center)]))
                            #         except:
                            #             continue

                            #         if len(pc_list) > 0:
                            #             publish_tf = True
                            #             # this is the location of our object in space
                            #             tf_id = str(yolo.names[c])

                            #             # if the user passes a tf prefix, we append it to the object tf name here
                            #             if self._tf_prefix is not None:
                            #                 tf_id = self._tf_prefix + '/' + tf_id

                            #             tf_id = tf_id

                            #             point_x, point_y, point_z = pc_list[0]

                            #     # we'll publish a TF related to this object only once
                            #     if publish_tf:
                            #         # kinect here is mapped as camera_link
                            #         # object tf (x, y, z) must be
                            #         # passed as (z,-x,-y)
                            #         object_tf = [point_z, -point_x, -point_y]
                            #         frame = self._frame

                            #         # translate the tf in regard to the fixed frame
                            #         if self._global_frame is not None:
                            #             object_tf = np.array(trans) + object_tf
                            #             frame = self._global_frame

                            #         # this fixes #7 on GitHub, when applying the
                            #         # translation to the tf creates a vector that
                            #         # RViz just can'y handle
                            #         if object_tf is not None:
                            #             self._tfpub.sendTransform((object_tf),
                            #                                     tf.transformations.quaternion_from_euler(
                            #                                         0, 0, 0),
                            #                                     rospy.Time.now(),
                            #                                     tf_id,
                            #                                     frame)
                            # cv2.destroyAllWindows()

                except CvBridgeError as e:
                    print(e)
                except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException) as e:
                    print(e)


if __name__ == '__main__':
    rospy.init_node('people_launch', log_level=rospy.INFO)

    try:
        Detector().run()
    except KeyboardInterrupt:
        rospy.loginfo('Shutting down')