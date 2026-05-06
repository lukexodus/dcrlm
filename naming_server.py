#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Member 1 — Registry Architect
# Naming Server: handles REGISTER and LOOKUP requests.

import socket
import threading
import sys
import argparse
from config import NAMING_SERVER_PORT

