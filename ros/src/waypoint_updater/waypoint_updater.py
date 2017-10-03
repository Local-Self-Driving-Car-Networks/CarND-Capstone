#!/usr/bin/env python

import rospy
import datetime
import tf.transformations
from geometry_msgs.msg import PoseStamped, Point
from std_msgs.msg import Int32, Float32
from styx_msgs.msg import Lane, Waypoint

import math

'''
This node will publish waypoints from the car's current position to some `x` distance ahead.

As mentioned in the doc, you should ideally first implement a version which does not care
about traffic lights or obstacles.

Once you have created dbw_node, you will update this node to use the status of traffic lights too.

Please note that our simulator also provides the exact location of traffic lights and their
current status in `/vehicle/traffic_lights` message. You can use this message to build this node
as well as to verify your TL classifier.

TODO (for Yousuf and Aaron): Stopline location for each traffic light.
'''

LOOKAHEAD_WPS = 240 # Number of waypoints we will publish. 
# tested at speeds up to 115 mph


# takes geometry_msgs/Point
def point_dist_sq(a, b):
    dx = a.x-b.x
    dy = a.y-b.y
    dz = a.z-b.z
    return dx*dx+dy*dy+dz*dz

# takes geometry_msgs/Point
def point_dist(a, b):
    return math.sqrt(point_dist_sq(a, b))

# takes styx_msgs/Waypoint
# returns geometry_msgs/Point
def waypoint_to_point(wp):
    point = wp.pose.pose.position
    return point

# takes styx_msgs/PoseStamp
# returns geometry_msgs/Point
def pose_to_point(pose):
    point = pose.pose.position
    return point

def waypoints_to_vec(a, b):
    return (b.x-a.x, b.y-a.y)

def dot_prod(a, b):
    return a[0]*b[0]+a[1]*b[1]

# takes 3 styx_msgs/Waypoints
# returns ratio of distance that b,
# projected onto line ac, is between
# a and c (ratio is 0. if b is at a, and
# 1. if b is at c
def line_ratio(a, b, c):
    ac = waypoints_to_vec(a, c)
    ab = waypoints_to_vec(a, b)
    bc = waypoints_to_vec(b, c)
    da = dot_prod(ab, ac)
    # dc = dot_prod(bc, ac)
    ac_dist = point_dist(a, c)
    return da/ac_dist

class WaypointUpdater(object):
    def __init__(self):
        rospy.init_node('waypoint_updater')

        rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb)
        rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb)

        # Add a subscriber for /traffic_waypoint and /obstacle_waypoint below
        rospy.Subscriber('/traffic_waypoint', Int32, self.traffic_cb)
        # But there is no /obstacle_waypoint topic, or Obstacle Detection node
        # rospy.Subscriber('/obstacle_waypoint', Lane, self.obstacle_cb)


        self.final_waypoints_pub = rospy.Publisher('final_waypoints', Lane, queue_size=1)
        self.next_waypoint_pub = rospy.Publisher('next_waypoint', Int32, queue_size=1)
        self.tl_distance_pub = rospy.Publisher('tl_distance', Float32, queue_size=1)
        self.wps = []
        self.wp_ss = []
        # self.full_wps = []
        self.prev_pt = Point()
        self.prev_index = -1
        self.next_pt = -1

        # TODO: Add other member variables you need below

        rospy.spin()


    '''
    PoseStamped:
    std_msgs/Header header
      uint32 seq
      time stamp
      string frame_id
    geometry_msgs/Pose pose
      geometry_msgs/Point position
        float64 x
        float64 y
        float64 z
      geometry_msgs/Quaternion orientation
        float64 x
        float64 y
        float64 z
        float64 w
    '''

    # takes styx_msgs/PoseStamp
    # returns i value of nearest waypoint in self.wps
    def nearest_waypoint(self, pose):
        ppt = pose_to_point(pose)
        prev_dist = point_dist_sq(ppt, self.prev_pt)
        # tested for speeds up to 115 mph
        wp_ahead = 200
        if prev_dist > .5*self.avg_wp_dist*wp_ahead:
            rospy.logwarn("nearest_waypoint: resetting")
            self.prev_index = -1
        self.prev_pt = ppt
        rg = range(0, len(self.wps))
        if self.prev_index > -1:
            rg = range(max(0, self.prev_index-5), min(len(self.wps), self.prev_index+wp_ahead+1))
        mindist = 0.
        mini = -1
        for i in rg:
            wp = self.wps[i]
            wpt = waypoint_to_point(wp)
            dsq = point_dist_sq(wpt, ppt)
            if mini < 0 or dsq < mindist:
                mini = i
                mindist = dsq
        self.prev_index = mini
        if mini == rg[0] or mini == rg[-1]:
            rospy.logwarn("nearest endpoint at end of range: %d %d %d", mini, rg[0], rg[-1])
            self.prev_index = -1
        return mini

    # takes styx_msgs/PoseStamp
    # returns i value of next waypoint in self.wps
    # ("next" assuming car is traversing the waypoints
    # in increasinge order)
    def next_waypoint(self, pose):
        ept = pose_to_point(pose)
        cur = self.nearest_waypoint(pose)
        nwps = len(self.wps)
        if nwps == 0 or cur < 0 or cur > len(self.wps)-1:
            rospy.logwarn("next_waypoint problem %d %d", len(self.wps), cur)
            return -1
        cpt = waypoint_to_point(self.wps[cur])
        prev = (cur+nwps-1)%nwps
        ppt = waypoint_to_point(self.wps[prev])
        nxt = (cur+1)%nwps
        npt = waypoint_to_point(self.wps[nxt])
        eratio = line_ratio(ppt, ept, npt)
        cratio = line_ratio(ppt, cpt, npt)
        if eratio > cratio:
            cur = nxt
        return cur


    def pose_cb(self, msg):
        # TODO: Implement
        # rospy.loginfo("Pose %d %s %s", msg.header.seq, msg.header.stamp, msg.header.frame_id)
        # rospy.loginfo("%s", msg.pose)
        # rospy.loginfo("Pose %s", msg.header)
        # rospy.loginfo("Pose %d", msg.header.seq)

        # Don't process if waypoints are not yet loaded
        if len(self.wps) == 0:
            return
        seq = msg.header.seq
        if seq%1 != 0:
            return
        q = msg.pose.orientation
        xyz = msg.pose.position
        (roll, pitch, yaw) = tf.transformations.euler_from_quaternion([q.x, q.y, q.z, q.w])
        ts = msg.header.stamp.secs + 1.e-9*msg.header.stamp.nsecs
        dtime = datetime.datetime.fromtimestamp(ts)
        dts = dtime.strftime("%H:%M:%S.%f")
        # near_pt is only used for testing
        # near_pt = self.nearest_waypoint(msg)
        next_pt = self.next_waypoint(msg)
        self.next_pt = next_pt
        near_pt = 0
        if next_pt < 0:
            return
        if seq%5 == 0:
            pass
            # rospy.loginfo("Pose %d %.6f %f %f  %f %d %d", seq, ts, xyz.x, xyz.y, math.degrees(yaw), near_pt, next_pt)
        # The consumer of the final_waypoints message
        # doesn't seem to care about anything except waypoint pose.pose
        # and waypoint twist.twist.linear.x
        olane = Lane()
        olane.header.frame_id = '/world'
        olane.header.stamp = rospy.Time(0)
        sz = len(self.wps)
        # may add fewer points if near the end of the track
        '''
        for i in range(0, LOOKAHEAD_WPS):
            if i >= sz:
                break
            wp = self.wps[i+next_pt]
            olane.waypoints.append(wp)
        '''
        wpsz = len(self.wps)
        end_pt = next_pt+LOOKAHEAD_WPS
        past_zero_pt = end_pt - wpsz
        end_pt = min(end_pt, wpsz)
        olane.waypoints=self.wps[next_pt:end_pt]
        # Handle case where we are near the end of the track;
        # add points at the beginning of the track
        if past_zero_pt > 0:
            olane.waypoints.extend(self.wps[:past_zero_pt])
        # if msg.header.seq % 20 == 0:
        #     rospy.loginfo("%s", olane)

        # TODO: for each waypoint, set velocity to appropriate
        # value; see functions below for getting and setting
        # waypoint velocity

        self.final_waypoints_pub.publish(olane)
        self.next_waypoint_pub.publish(next_pt)


    '''
    styx_msgs/Lane:
    std_msgs/Header header
      uint32 seq
      time stamp
      string frame_id
    styx_msgs/Waypoint[] waypoints
      geometry_msgs/PoseStamped pose
        std_msgs/Header header
          uint32 seq
          time stamp
          string frame_id
        geometry_msgs/Pose pose
          geometry_msgs/Point position
            float64 x
            float64 y
            float64 z
          geometry_msgs/Quaternion orientation
            float64 x
            float64 y
            float64 z
            float64 w
      geometry_msgs/TwistStamped twist
        std_msgs/Header header
          uint32 seq
          time stamp
          string frame_id
        geometry_msgs/Twist twist
          geometry_msgs/Vector3 linear
            float64 x
            float64 y
            float64 z
          geometry_msgs/Vector3 angular
            float64 x
            float64 y
            float64 z
    '''

    def waypoints_cb(self, waypoints):
        # rospy.loginfo("Waypoints", waypoints)
        # rospy.loginfo("Waypoints %d\n%s", len(waypoints.waypoints), waypoints.waypoints[0])
        # rospy.loginfo("Waypoints\n%s", waypoints.header)

        # TODO: Implement
        if len(waypoints.waypoints) == len(self.wps):
            # rospy.loginfo("Waypoints: same as before")
            return
        '''
        local_wps = []
        for wp in waypoints.waypoints:
            # just position; ignoring yaw
            # and speed information
            # x = wp.pose.pose.position.x
            # y = wp.pose.pose.position.y
            local_wps.append(wp.pose.pose.position)
            # v = wp.twist.twist.linear.x
            # local_wps.append((x,y,v))

        self.wps = local_wps
        '''
        self.wps = waypoints.waypoints

        s = 0.
        prev_pt = waypoint_to_point(self.wps[0])
        for i in range(len(self.wps)+1):
            cur_pt = waypoint_to_point(self.wps[i%(len(self.wps))])
            d = point_dist(prev_pt, cur_pt)
            s += d
            # if i < 10 or i > len(self.wps)-10:
            #     print(i, s)
            self.wp_ss.append(s)
            prev_pt = cur_pt

        self.avg_wp_dist = 0.
        for i in range(1, len(self.wps)):
            pt = waypoint_to_point(self.wps[i])
            ppt = waypoint_to_point(self.wps[i-1])
            d = point_dist(pt, ppt)
            self.avg_wp_dist += d
        self.avg_wp_dist /= len(self.wps) - 1


        rospy.loginfo("Waypoints: now have %d avg dist %f", len(self.wps), self.avg_wp_dist)

        ''' 
        Code below is to see how yaw can be computed from
        x,y points.  Conclusion: yaw in the input file at point i 
        appears to be computed by finding the angle of the line 
        that goes from point i-1 to point i+1.
        '''

            
        '''
        rospy.loginfo("yaw:")
        # rg = range(0,10)
        # rg.extend(range(len(self.wps)-10, len(self.wps)))
        # rg = range(1823,1833)
        rg = range(0,len(self.wps))
        rp = 0.
        rn = 0.
        rb = 0.
        emin = 0.
        emax = 0.
        for i in rg:
            wp = self.wps[i]
            q = wp.pose.pose.orientation
            (roll, pitch, yaw) = tf.transformations.euler_from_quaternion([q.x, q.y, q.z, q.w])
            x = wp.pose.pose.position.x
            y = wp.pose.pose.position.y
            cap = 0.
            can = 0.
            cab = 0.
            if i > 0 and i < len(self.wps)-1:
                wpp = self.wps[i-1]
                px = wpp.pose.pose.position.x
                py = wpp.pose.pose.position.y
                wpn = self.wps[i+1]
                nx = wpn.pose.pose.position.x
                ny = wpn.pose.pose.position.y
                cap = math.atan2(y-py, x-px) - yaw
                can = math.atan2(ny-y, nx-x) - yaw
                cab = math.atan2(ny-py, nx-px) - yaw
                rp += cap*cap
                rn += can*can
                rb += cab*cab
                err = math.degrees(cab)
                if err > 180:
                    err -= 360
                if err < -180:
                    err += 360
                emin = min(err, emin)
                emax = max(err, emax)
            # rospy.loginfo("%d %f %f %f %f  %.3f %.2f", i, yaw, cap, can, cab, x, y)
        rospy.loginfo("err min max %f %f", math.radians(emin), math.radians(emax))
        '''

        pass

    def traffic_cb(self, msg):
        # TODO: Callback for /traffic_waypoint message. Implement
        # print("tcb", msg)
        # If next_tl is positive, then next_tl has the waypoint
        # of the next red light.  If next_tl is negative, then
        # abs(next_tl) has the waypoint of the next light, and the
        # negative sign signals that the next light is NOT red.
        next_tl = msg.data
        sgn = 1
        if next_tl < 0:
            sgn = -1
            next_tl *= -1
        dist = -1.0
        if self.next_pt >= 0 and next_tl >= 0:
            sz = len(self.wps)
            dist = self.wp_ss[next_tl] - self.wp_ss[self.next_pt]
            if dist < 0:
                dist += self.wp_ss[sz]

        # Output: distance to next light.  If output is positive,
        # it means that the next light is red.  If distance is negative,
        # it means that the next light is NOT red, and abs(distance)
        # gives the distance to this non-red light.
        self.tl_distance_pub.publish(sgn*dist)
        # print("ds", dist)

    def obstacle_cb(self, msg):
        # This is never called
        pass

    def get_waypoint_velocity(self, waypoint):
        return waypoint.twist.twist.linear.x

    def set_waypoint_velocity(self, waypoints, waypoint, velocity):
        waypoints[waypoint].twist.twist.linear.x = velocity

'''
    def distance(self, waypoints, wp1, wp2):
        dist = 0
        dl = lambda a, b: math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2  + (a.z-b.z)**2)
        for i in range(wp1, wp2+1):
            dist += dl(waypoints[wp1].pose.pose.position, waypoints[i].pose.pose.position)
            wp1 = i
        return dist
'''


if __name__ == '__main__':
    try:
        WaypointUpdater()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start waypoint updater node.')
