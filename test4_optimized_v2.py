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

class OptimizedNoiseRenderer:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        
        # Smart caching only for static/repeated patterns
        self.enable_cache = True
        self.noise_cache = {}
        self.cache_max_size = 2000  # Smaller cache for better performance
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Pre-allocate output buffers 
        self.output_parts = []
        
        # Pre-compile escape sequences for better performance
        self.escape_start = "\x1B[48;2;"
        self.escape_end = "m "
        
        # For vectorized operations
        self.last_frame_time = 0
        
    def get_noise_optimized(self, x, y, z):
        """Optimized noise calculation with selective caching"""
        if not self.enable_cache:
            return float(pnoise3(x, y, z))
            
        # Only cache if coordinates are "round enough" to get cache hits
        # Round to 1 decimal place for better hit ratio vs cache size
        key = (round(x, 1), round(y, 1), round(z, 1))
        
        if key in self.noise_cache:
            self.cache_hits += 1
            return self.noise_cache[key]
        
        # Calculate noise value
        value = float(pnoise3(x, y, z))
        self.cache_misses += 1
        
        # Manage cache size more aggressively
        if len(self.noise_cache) >= self.cache_max_size:
            # Remove half the cache when full (keeps most recent)
            items_to_remove = list(self.noise_cache.keys())[:self.cache_max_size // 2]
            for k in items_to_remove:
                del self.noise_cache[k]
        
        self.noise_cache[key] = value
        return value
    
    def render_frame_fast(self, xoffset, yoffset, zoffset, mx, b, framecount):
        """Highly optimized frame rendering focused on real bottlenecks"""
        self.output_parts.clear()
        
        # Batch process pixels and minimize function calls
        for y in range(self.height):
            ypos = y/5 + yoffset
            
            # Build line in one go 
            line_parts = []
            for x in range(self.width):
                xpos = x/10 + xoffset
                
                # Direct noise calculation (avoid caching overhead for simple cases)
                noiseval = self.get_noise_optimized(xpos, ypos, zoffset)
                val = int(noiseval * mx + b)
                
                # Clamp efficiently
                if val < 0:
                    val = 0
                elif val > 255:
                    val = 255
                
                # Build escape sequence directly
                r, g, b_color = val, 255-val, framecount % 255
                line_parts.append(f"{self.escape_start}{r};{g};{b_color}{self.escape_end}")
            
            self.output_parts.append(''.join(line_parts))
        
        return self.output_parts
    
    def get_cache_stats(self):
        total = self.cache_hits + self.cache_misses
        hit_ratio = (self.cache_hits / total * 100) if total > 0 else 0
        return hit_ratio, len(self.noise_cache)

# Main application with performance optimizations
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

# Optimized constants
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
renderer = OptimizedNoiseRenderer(width, height)
perf_monitor = PerformanceMonitor()

# Open debug file only once
fh = open("debug.txt", "w")

# Enable mouse tracking
sys.stdout.write("\x1B[?1003h\x1B[?1015h\x1B[?1006h")
sys.stdout.flush()

framecount = 0
last_size_check = 0

# Pre-allocate main output buffer
main_output = []

while True:
    frame_start = time.time()
    framecount += 1
    
    # Handle input efficiently
    event = screen.getch()
    
    # Check screen size less frequently
    if framecount - last_size_check > 30:
        new_height, new_width = screen.getmaxyx()
        new_height = new_height - 1
        if new_width != width or new_height != height:
            width, height = new_width, new_height
            renderer = OptimizedNoiseRenderer(width, height)
        last_size_check = framecount
    
    # Optimized input handling
    instream = ""
    if select.select([sys.stdin], [], [], 0)[0]:
        instream = sys.stdin.read(1000)  # Read more at once
    
    # Parse mouse input efficiently 
    if instream:
        # Focus on most common mouse events only
        parts = instream.replace("\x1b[<", "").split("M")
        for part in parts:
            if ";" in part:
                try:
                    elements = part.split(";")
                    if len(elements) >= 3:
                        if elements[0] == "35":
                            mousex = int(elements[1])
                            mousey = int(elements[2])
                        elif elements[0] == "65":
                            zvelocity -= 0.01
                        elif elements[0] == "64":
                            zvelocity += 0.01
                except (ValueError, IndexError):
                    continue
    
    if event == ord("q"):
        break
    
    # Update positions (batch these calculations)
    xcentre = width/2
    ycentre = height/2
    
    # Simplified velocity calculations
    xvelocity = (mousex - xcentre) * 0.001
    yvelocity = (mousey - ycentre) * 0.001
    
    xoffset += xvelocity
    yoffset += yvelocity
    zoffset += zvelocity
    
    # Render frame with optimizations
    frame_lines = renderer.render_frame_fast(xoffset, yoffset, zoffset, mx, b, framecount)
    
    # Build complete output in one buffer
    main_output.clear()
    main_output.append("\x1B[1;1H\x1B[0m")
    
    # Header with performance info
    current_fps = perf_monitor.get_fps()
    hit_ratio, cache_size = renderer.get_cache_stats()
    header = f"Mouse: {mousex:3d},{mousey:3d} Vel: {xvelocity:.3f},{yvelocity:.3f},{zvelocity:.3f} FPS: {current_fps:.1f} Cache: {hit_ratio:.0f}%"
    main_output.append(header)
    main_output.append("\x1B[1E")
    
    # Add all frame lines
    for line in frame_lines:
        main_output.append(line)
        main_output.append("\x1B[1E")
    
    # Single output operation
    sys.stdout.write(''.join(main_output))
    sys.stdout.flush()
    
    # Update performance monitoring
    frame_time = perf_monitor.update()
    
    # Adaptive frame rate
    elapsed = time.time() - frame_start
    if elapsed < target_frame_time:
        time.sleep(target_frame_time - elapsed)
    
    # Update dynamic range less frequently
    if framecount % 10 == 0:
        [mx, b] = mxplusb(0, minfound, 255, maxfound)

# Cleanup
curses.curs_set(1)
curses.endwin()
fh.close()
signal_handler(0, 0)