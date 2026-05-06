#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Member 2 — send_json, recv_json, get_local_ip
# Member 3 — LamportClock, sort_queue, build_queue_update_msg,
#             simulate_resource_use, check_lock_timeout

import socket
import threading
import json
import struct
import time
from config import *

