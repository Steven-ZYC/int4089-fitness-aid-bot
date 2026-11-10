"""Windows-side IMU zero-drift handling and 3D position panel.

The package consumes the BMI160 CSV stream documented in
firmware/esp32-camera/BMI160_SixAxis/BMI160_SixAxis.ino and applies a
zero-drift profile (gyroscope bias, static detection, complementary
attitude filter, ZUPT-constrained integration) before visualisation.
"""

__version__ = "0.1.0"
