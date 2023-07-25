import os
import time

# Make sure tests use a fixed, non-UTC local timezone
os.environ["TZ"] = "Africa/Addis_Ababa"
time.tzset()
