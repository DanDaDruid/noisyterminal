#!/usr/bin/python3 -u

from noise import pnoise3
from scipy.interpolate import interp1d
import sys
sys.stdout.softspace=False;
import time;
import curses;
import signal
import select;
import os;

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
	curses.endwin();

	print("Min: %5f" % minfound);
	print("Max: %5f" % maxfound);

	sys.exit(0)

def mxplusb(exp1, act1, exp2, act2):
	m = (exp2 - exp1) / (act2 - act1);
	b = exp1 - (m * act1);
	return [m, b]

signal.signal(signal.SIGINT, signal_handler)

screen = curses.initscr()
curses.curs_set(0)
screen.keypad(1)
curses.mouseinterval(0)

curses.mousemask(1)
screen.nodelay(1)
curses.noecho()
curses.raw()
curses.cbreak()

# Turn off buffering for stdin...
#sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', buffering=0)


# printf("\033[?1003h\n"); // Makes the terminal report mouse movement events
#sys.stdout.write('\033[?1003h');

curses.curs_set(0);

#curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
curses.mousemask(curses.ALL_MOUSE_EVENTS)

# https://en.wikipedia.org/wiki/ANSI_escape_code
# 38 to set the fireground, 48 to set the background

# use function to map from one range to another... SLOW!!!
mapper = interp1d(
	#[-1, 1], # input range
	[-0.88414, 0.884236],
	[0, 255], # output range which is greyscale
	fill_value="extrapolate"
)

# http://gtcentral.server5.lan/mxplusb.php?exp1=0&act1=-0.88414&exp2=255&act2=0.884236
maxval = 255
mx = 144.2001022407
b = 127.49307839509

# http://gtcentral.server5.lan/mxplusb.php?exp1=0&act1=-1&exp2=255&act2=1
maxval = 255
mx = 127.5
b = 127.5

width = 80;
height = 10;

height, width = screen.getmaxyx()
# We're going to use the top line for info so reduce by 1...
height = height - 1;
fps = 30;

z = 0;

minfound = 0.0;
maxfound = 0.0;

mouseid = mousex = mousey = mousez = mousebstate = ""

fh = open("debug.txt", "w");

mousex = 0;
mousey = 0;

xoffset = 0;
yoffset = 0;
zoffset = 0;

xvelocity = 0.01;
yvelocity = 0.01;
zvelocity = 0;

sys.stdout.write("\x1B[?1003h");

#echo -e "\e[?1003h\e[?1015h\e[?1006h"
sys.stdout.write("\x1B[?1003h\x1B[?1015h\x1B[?1006h");

instream = ""; # ...keep track of inputstream

#while(z < 100):
framecount = 0
while(1):
	framecount = framecount + 1;
	# Any mouse stuff?...
	event = screen.getch()
	#print(event);

	height, width = screen.getmaxyx()
	# We're going to use the top line for info so reduce by 1...
	height = height - 1;

	instream = ""
	while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
		#data = sys.stdin.buffer.read(1);
		data = sys.stdin.read(1);
		instream = instream + str(data)


	# https://stackoverflow.com/questions/5966903/how-to-get-mousemove-and-mouseclick-in-bash/58390575#58390575
	if instream != "":
		#fh.write(str(instream) + "");
		# Parse out instream...
		instreamelements1 = instream.replace("\x1b", "").replace("[", "").replace("<", "").split("M")

		for entry in instreamelements1:
			if entry == "":
				continue;
			metainfo = entry.split(";");
			if(metainfo[0] == "35"):
				mousex = int(metainfo[1]);
				mousey = int(metainfo[2]);
			elif(metainfo[0] == "65"):
				zvelocity = zvelocity - 0.01;
			elif(metainfo[0] == "64"):
				zvelocity = zvelocity + 0.01;
			else:
				fh.write(", ".join(metainfo) + "\n");


		#fh.write(instreamelements.join("\n"));
		#fh.write("\n".join(instreamelements));

		fh.flush();

	if event == ord("q"): break

	################################################################################
	# Determine the velocity from the mouse offset from the centre...
	xcentre = width/2;
	[Xmx, Xb] = mxplusb(-1, 0, 1, width)
	xvelocity = mousex * Xmx + Xb

	ycentre = height/2;
	[Ymx, Yb] = mxplusb(-1, 0, 1, height)
	yvelocity = mousey * Ymx + Yb

	xoffset += xvelocity;
	yoffset += yvelocity;
	zoffset += zvelocity;

	################################################################################

	# Send the cursor to the top left...
	sys.stdout.write("\x1B[1;1H");
	sys.stdout.write("\x1B[0m");
	#sys.stdout.write("z = %d - min = %.5f - max = %.5f " %(z, minfound, maxfound));
	# Outout mouse bits...
	sys.stdout.write("Mouse: %d, %d " % (mousex, mousey));
	#sys.stdout.write("MX, B = %.2f, %.2f" % (mx, b));
	#sys.stdout.write("FPS = %d " % fps);
	sys.stdout.write("xvel = %.2f, yvel = %.2f, zvel = %.2f, " % (xvelocity, yvelocity, zvelocity));

	sys.stdout.write("xoff = %.2f, yoff = %.2f, zoff = %.2f " % (xoffset, yoffset, zoffset));

	sys.stdout.write("\x1B[%dE" % 1); # Move down one line

	for y in range(height):
		# Send the cursor to the next line...
		linedata = "";
		for x in range(width):
			#val = int(mapper(float(pnoise3(x/10, y/10, z/10))));

			# Dteermine where we are in perlin space...
			xpos = x/10 + xoffset;
			ypos = y/5 + yoffset;
			zpos = z/5 + zoffset;

			#noiseval = float(pnoise3(x/10, y/5, z/20)); // Travel throught the z plane (formwards)
			#noiseval = float(pnoise3(x/10 + z/5, y/5, 0)); # travel along the X axis right
			noiseval = float(pnoise3(xpos, ypos, zpos)); # travel along the Y axis
			val = noiseval * mx + b;
			if(val > maxval):
				val = maxval

			minfound = min(minfound, noiseval);
			maxfound = max(maxfound, noiseval);

			# print("%.5f" % val)
			#linedata += "\x1B[48;2;%d;%d;%dm \x1B[0m" % (val, val, val) # RGB Values
			linedata += "\x1B[48;2;%d;%d;%dm " % (val, 255-val, framecount % 255) # RGB Values

			# sys.stdout.write("%d, %d, %d" % (x, y, z)),

		sys.stdout.write(linedata)
		sys.stdout.write("\x1B[%dE" % 1); # Move down one line
		#time.sleep(0.01);
	time.sleep(1/fps);

	# Determine the new mx and b values...
	# http://gtcentral.server4.lan/mxplusb.php?exp1=0&act1=-1&exp2=255&act2=1
	# def mxplusb(exp1, act1, exp2, act2):

	[mx, b] = mxplusb(0, minfound, 255, maxfound)

curses.curs_set(1)
curses.endwin();
signal_handler(0, 0)
