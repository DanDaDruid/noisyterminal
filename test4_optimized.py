#!/usr/bin/python3 -u

from noise import pnoise3
import sys
sys.stdout.softspace=False
import time
import curses
import signal
import select
import os
import numpy as np
from collections import deque

def tb_lineno(tb):
    c = tb.tb_frame.f_code
    if not hasattr(tb.tb_frame.f_code, 'co_lnotab'):
        return tb.tb_lineno
    line = tb.tb_frame.f_code.co_firstlineno
    addr = 0
    for i in range(0, len(tb.tb_frame.f_code.co_lnotab), 2):
        addr = addr + tb.tb_frame.f_code.co_lnotab[i]
        if addr > tb.tb_lasti:
            break
        line = line + tb.tb_frame.f_code.co_lnotab[i+1]
    return line

def signal_handler(sig, frame):
    print('Exiting...')
    curses.curs_set(1)
    curses.endwin()
    print("Min: %5f" % minfound)
    print("Max: %5f" % maxfound)
    sys.exit(0)

def mxplusb(exp1, act1, exp2, act2):
    m = (exp2 - exp1) / (act2 - act1)
    b = exp1 - (m * act1)
    return [m, b]

class PerformanceMonitor:
    def __init__(self, window_size=60):
        self.frame_times = deque(maxlen=window_size)
        self.last_frame_time = time.time()
    
    def update(self):
        current_time = time.time()
        frame_time = current_time - self.last_frame_time
        self.frame_times.append(frame_time)
        self.last_frame_time = current_time
        return frame_time
    
    def get_fps(self):
        if len(self.frame_times) < 2:
            return 0
        return 1.0 / (sum(self.frame_times) / len(self.frame_times))

class NoiseRenderer:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        # Pre-allocate buffers
        self.noise_cache = {}
        self.cache_max_size = 10000
        self.frame_buffer = []
        
        # Pre-calculate coordinate grids for vectorization
        self.x_coords = np.arange(width)
        self.y_coords = np.arange(height)
        
        # Pre-allocate string buffers
        self.line_buffers = [[] for _ in range(height)]
        
        # Optimization: pre-calculate escape sequence parts
        self.rgb_template = "\x1B[48;2;{};{};{}m "
        
    def get_noise_cached(self, x, y, z):
        """Cached noise lookup with LRU-style eviction"""
        key = (round(x, 2), round(y, 2), round(z, 2))  # Reduce precision for better cache hits
        
        if key in self.noise_cache:
            return self.noise_cache[key]
        
        # Calculate noise value
        value = float(pnoise3(x, y, z))
        
        # Simple cache eviction when full
        if len(self.noise_cache) >= self.cache_max_size:
            # Remove oldest 20% of cache entries
            items_to_remove = list(self.noise_cache.keys())[:self.cache_max_size // 5]
            for k in items_to_remove:
                del self.noise_cache[k]
        
        self.noise_cache[key] = value
        return value
    
    def render_frame_optimized(self, xoffset, yoffset, zoffset, mx, b, framecount):
        """Optimized frame rendering with reduced allocations and I/O"""
        # Clear frame buffer
        self.frame_buffer.clear()
        
        # Batch calculate noise values for better cache locality
        for y in range(self.height):
            # Clear line buffer
            line_parts = self.line_buffers[y]
            line_parts.clear()
            
            ypos = y/5 + yoffset
            
            for x in range(self.width):
                xpos = x/10 + xoffset
                zpos = zoffset
                
                # Use cached noise calculation
                noiseval = self.get_noise_cached(xpos, ypos, zpos)
                val = int(noiseval * mx + b)
                val = min(max(val, 0), 255)  # Clamp instead of if statement
                
                # Pre-format RGB values
                r, g, b_color = val, 255-val, framecount % 255
                line_parts.append(self.rgb_template.format(r, g, b_color))
            
            # Join line parts once per line instead of concatenating repeatedly
            self.frame_buffer.append(''.join(line_parts))
        
        return self.frame_buffer

# Performance optimizations applied
signal.signal(signal.SIGINT, signal_handler)

screen = curses.initscr()
curses.curs_set(0)
screen.keypad(1)
curses.mouseinterval(0)
curses.mousemask(curses.ALL_MOUSE_EVENTS)
screen.nodelay(1)
curses.noecho()
curses.raw()
curses.cbreak()

# Cache commonly used values
maxval = 255
mx = 127.5
b = 127.5

width = 80
height = 10

height, width = screen.getmaxyx()
height = height - 1  # Reserve top line for info

fps = 30
target_frame_time = 1.0 / fps

z = 0
minfound = 0.0
maxfound = 0.0

mousex = 0
mousey = 0
xoffset = 0
yoffset = 0
zoffset = 0
xvelocity = 0.01
yvelocity = 0.01
zvelocity = 0

# Initialize optimized renderer
renderer = NoiseRenderer(width, height)
perf_monitor = PerformanceMonitor()

# Open debug file only once
fh = open("debug.txt", "w")

# Enable mouse tracking
sys.stdout.write("\x1B[?1003h\x1B[?1015h\x1B[?1006h")
sys.stdout.flush()  # Ensure it's sent immediately

framecount = 0
instream = ""

# Pre-allocate buffers for input handling
input_buffer = []

while True:
    frame_start = time.time()
    framecount += 1
    
    # Handle input more efficiently
    event = screen.getch()
    
    # Get current screen size (only if it might have changed)
    if framecount % 30 == 0:  # Check every 30 frames instead of every frame
        height, width = screen.getmaxyx()
        height = height - 1
        if renderer.width != width or renderer.height != height:
            renderer = NoiseRenderer(width, height)  # Recreate if size changed
    
    # Optimized input stream handling
    instream = ""
    input_ready = select.select([sys.stdin], [], [], 0)[0]
    if input_ready:
        while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            data = sys.stdin.read(1)
            instream += data
    
    # Parse mouse input more efficiently
    if instream:
        # Simplified parsing - focus on the most common cases
        instreamelements1 = instream.replace("\x1b", "").replace("[", "").replace("<", "").split("M")
        
        for entry in instreamelements1:
            if not entry:
                continue
            metainfo = entry.split(";")
            if len(metainfo) >= 3:
                try:
                    if metainfo[0] == "35":
                        mousex = int(metainfo[1])
                        mousey = int(metainfo[2])
                    elif metainfo[0] == "65":
                        zvelocity -= 0.01
                    elif metainfo[0] == "64":
                        zvelocity += 0.01
                except (ValueError, IndexError):
                    pass  # Ignore malformed input
    
    if event == ord("q"):
        break
    
    # Update velocities and offsets
    xcentre = width/2
    [Xmx, Xb] = mxplusb(-1, 0, 1, width)
    xvelocity = mousex * Xmx + Xb
    
    ycentre = height/2
    [Ymx, Yb] = mxplusb(-1, 0, 1, height)
    yvelocity = mousey * Ymx + Yb
    
    xoffset += xvelocity
    yoffset += yvelocity
    zoffset += zvelocity
    
    # Build frame output in a single buffer to minimize I/O
    output_buffer = []
    
    # Header line
    output_buffer.append("\x1B[1;1H\x1B[0m")
    current_fps = perf_monitor.get_fps()
    header = f"Mouse: {mousex}, {mousey} xvel = {xvelocity:.2f}, yvel = {yvelocity:.2f}, zvel = {zvelocity:.2f}, xoff = {xoffset:.2f}, yoff = {yoffset:.2f}, zoff = {zoffset:.2f} FPS: {current_fps:.1f}"
    output_buffer.append(header)
    output_buffer.append("\x1B[1E")  # Move down one line
    
    # Render frame using optimized renderer
    frame_lines = renderer.render_frame_optimized(xoffset, yoffset, zoffset, mx, b, framecount)
    
    # Add frame lines to output buffer
    for line in frame_lines:
        output_buffer.append(line)
        output_buffer.append("\x1B[1E")  # Move down one line
    
    # Single write operation for entire frame
    sys.stdout.write(''.join(output_buffer))
    sys.stdout.flush()
    
    # Update performance monitoring
    frame_time = perf_monitor.update()
    
    # Adaptive frame rate - skip sleep if we're running slow
    elapsed = time.time() - frame_start
    if elapsed < target_frame_time:
        time.sleep(target_frame_time - elapsed)
    
    # Update min/max tracking for noise values
    if framecount % 10 == 0:  # Update less frequently
        [mx, b] = mxplusb(0, minfound, 255, maxfound)

# Cleanup
curses.curs_set(1)
curses.endwin()
fh.close()
signal_handler(0, 0)