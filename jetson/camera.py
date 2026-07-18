"""
Warehouse AGV - Intel RealSense Camera Interface

Captures aligned RGB + Depth frames from Intel RealSense D4xx camera.
Provides downscaled frames for processing and optional further downscaling for network transmission.
"""

import time
import numpy as np
import cv2

try:
    import pyrealsense2 as rs
except ImportError:
    print("[Camera] WARNING: pyrealsense2 not available - using mock mode")
    rs = None

import config


class RealSenseCamera:
    """Intel RealSense D435/D455 camera interface."""

    def __init__(self):
        self.pipeline = None
        self.align = None
        self.running = False
        self.intrinsics = None

        # Latest frames
        self._color_frame = None
        self._depth_frame = None
        self._timestamp = 0

    def start(self) -> bool:
        """Initialize and start the RealSense pipeline."""
        if rs is None:
            print("[Camera] pyrealsense2 not available")
            return False

        try:
            self.pipeline = rs.pipeline()
            cfg = rs.config()

            # Configure streams
            cfg.enable_stream(
                rs.stream.color,
                config.CAMERA_WIDTH,
                config.CAMERA_HEIGHT,
                rs.format.bgr8,
                config.CAMERA_FPS
            )
            cfg.enable_stream(
                rs.stream.depth,
                config.CAMERA_WIDTH,
                config.CAMERA_HEIGHT,
                rs.format.z16,
                config.CAMERA_FPS
            )

            # Start pipeline
            profile = self.pipeline.start(cfg)

            # Get depth sensor intrinsics for 3D projection
            depth_stream = profile.get_stream(rs.stream.depth).as_video_stream_profile()
            self.intrinsics = depth_stream.get_intrinsics()

            # Align depth to color
            self.align = rs.align(rs.stream.color)

            # Allow auto-exposure to stabilize
            for _ in range(30):
                self.pipeline.wait_for_frames()

            self.running = True
            print(f"[Camera] Started: {config.CAMERA_WIDTH}x{config.CAMERA_HEIGHT} @ {config.CAMERA_FPS}fps")
            return True

        except Exception as e:
            print(f"[Camera] ERROR starting: {e}")
            return False

    def stop(self):
        """Stop the camera pipeline."""
        if self.pipeline:
            self.pipeline.stop()
        self.running = False
        print("[Camera] Stopped")

    def get_frames(self):
        """
        Capture and return aligned color + depth frames.
        
        Returns:
            Tuple of (color_image, depth_image, depth_meters) or (None, None, None) on failure.
            - color_image: BGR numpy array, shape (PROCESS_HEIGHT, PROCESS_WIDTH, 3)
            - depth_image: uint16 numpy array, shape (PROCESS_HEIGHT, PROCESS_WIDTH)
            - depth_meters: float32 numpy array of depth in meters
        """
        if not self.running:
            return None, None, None

        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=1000)
            aligned_frames = self.align.process(frames)

            color_frame = aligned_frames.get_color_frame()
            depth_frame = aligned_frames.get_depth_frame()

            if not color_frame or not depth_frame:
                return None, None, None

            # Convert to numpy
            color_image = np.asanyarray(color_frame.get_data())
            depth_image = np.asanyarray(depth_frame.get_data())

            # Downscale for processing
            color_image = cv2.resize(
                color_image,
                (config.PROCESS_WIDTH, config.PROCESS_HEIGHT),
                interpolation=cv2.INTER_AREA
            )
            depth_image = cv2.resize(
                depth_image,
                (config.PROCESS_WIDTH, config.PROCESS_HEIGHT),
                interpolation=cv2.INTER_NEAREST
            )

            # Convert depth to meters (RealSense depth is in millimeters as uint16)
            depth_meters = depth_image.astype(np.float32) * 0.001

            self._color_frame = color_image
            self._depth_frame = depth_meters
            self._timestamp = time.time()

            return color_image, depth_image, depth_meters

        except Exception as e:
            print(f"[Camera] Frame capture error: {e}")
            return None, None, None

    def get_frame_for_planner(self, color_image: np.ndarray) -> bytes:
        """
        Prepare a compressed image for sending to the remote planner.
        Further downscales and JPEG compresses the image.
        
        Args:
            color_image: BGR image from get_frames()
            
        Returns:
            JPEG bytes ready for HTTP transmission
        """
        small = cv2.resize(
            color_image,
            (config.PLANNER_IMAGE_WIDTH, config.PLANNER_IMAGE_HEIGHT),
            interpolation=cv2.INTER_AREA
        )
        _, jpeg_bytes = cv2.imencode(
            '.jpg',
            small,
            [cv2.IMWRITE_JPEG_QUALITY, config.PLANNER_IMAGE_QUALITY]
        )
        return jpeg_bytes.tobytes()

    def depth_to_pointcloud(self, depth_meters: np.ndarray) -> np.ndarray:
        """
        Convert depth image to 3D point cloud using camera intrinsics.
        
        Args:
            depth_meters: float32 depth image in meters
            
        Returns:
            Nx3 numpy array of 3D points (x, y, z) in camera frame
        """
        if self.intrinsics is None:
            return np.array([])

        height, width = depth_meters.shape

        # Scale intrinsics to processing resolution
        fx = self.intrinsics.fx * (config.PROCESS_WIDTH / config.CAMERA_WIDTH)
        fy = self.intrinsics.fy * (config.PROCESS_HEIGHT / config.CAMERA_HEIGHT)
        cx = self.intrinsics.ppx * (config.PROCESS_WIDTH / config.CAMERA_WIDTH)
        cy = self.intrinsics.ppy * (config.PROCESS_HEIGHT / config.CAMERA_HEIGHT)

        # Create pixel coordinate grid
        u = np.arange(width)
        v = np.arange(height)
        u, v = np.meshgrid(u, v)

        # Deproject to 3D
        z = depth_meters
        x = (u - cx) * z / fx
        y = (v - cy) * z / fy

        # Filter out zero/invalid depth
        valid = z > 0.1  # Minimum 10cm
        points = np.stack([x[valid], y[valid], z[valid]], axis=-1)

        return points

    @property
    def latest_color(self) -> np.ndarray:
        """Get the most recently captured color frame."""
        return self._color_frame

    @property
    def latest_depth(self) -> np.ndarray:
        """Get the most recently captured depth frame (in meters)."""
        return self._depth_frame


# --- Quick test ---
if __name__ == "__main__":
    camera = RealSenseCamera()
    if camera.start():
        print("Capturing 5 frames...")
        for i in range(5):
            color, depth_raw, depth_m = camera.get_frames()
            if color is not None:
                print(f"  Frame {i}: color={color.shape}, depth range={depth_m.min():.2f}-{depth_m.max():.2f}m")
                points = camera.depth_to_pointcloud(depth_m)
                print(f"    Point cloud: {points.shape[0]} points")
            time.sleep(0.5)
        camera.stop()
    else:
        print("Failed to start camera")
