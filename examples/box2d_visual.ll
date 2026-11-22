# Live browser visualisation of the native llang physics engine.
# llang runs the simulation and writes the trajectory; the browser only draws it.

use the box2d module
use the json module

set gravity to call vec2 from box2d with x = 0, y = (0 minus 10)
set world to call new_world from box2d with gravity = gravity, dt = (1 divided by 60), vel_iters = 8, pos_iters = 3
set ball to call new_dynamic_body from box2d with x = 0, y = 0, radius = 1, density = 1
call add_body from box2d with world = world, body = ball

set ys to an empty list
set step to 0
repeat while step is less than 180
    call world_step from box2d with world = world
    set p to call body_position from box2d with body = ball
    add (item "y" of p) to ys
    set step to step plus 1
end repeat

set trajectory to call stringify from json with value = ys

set html to "<!DOCTYPE html>\n"
set html to html plus "<html lang='en'>\n<head><meta charset='utf-8'><title>llang physics engine — live</title>\n"
set html to html plus "<style>\n"
set html to html plus "body{background:#0b1120;color:#e2e8f0;font-family:system-ui,sans-serif;margin:0;padding:20px;display:flex;flex-direction:column;align-items:center}\n"
set html to html plus "h1{font-size:20px;color:#38bdf8;margin:0 0 4px}\n"
set html to html plus "p.sub{color:#94a3b8;font-size:13px;margin:0 0 12px}\n"
set html to html plus "canvas{background:#111c33;border:1px solid #334155;border-radius:10px}\n"
set html to html plus ".bar{margin:12px 0;display:flex;gap:8px}\n"
set html to html plus "button{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:8px 16px;cursor:pointer;font-size:14px}\n"
set html to html plus "button:hover{background:#1d4ed8}\n"
set html to html plus "#readout{font-family:ui-monospace,monospace;font-size:14px;color:#fbbf24}\n"
set html to html plus "</style></head><body>\n"
set html to html plus "<h1>llang physics engine — live simulation</h1>\n"
set html to html plus "<p class='sub'>Trajectory computed by the native box2d module in llang. The browser only draws it.</p>\n"
set html to html plus "<canvas id='c' width='420' height='420'></canvas>\n"
set html to html plus "<div class='bar'><button id='play'>Pause</button><button id='reset'>Restart</button></div>\n"
set html to html plus "<div id='readout'></div>\n"
set html to html plus "<script>\n"
set html to html plus "const ys=" plus trajectory plus ";\n"
set html to html plus "const c=document.getElementById('c'),g=c.getContext('2d'),out=document.getElementById('readout');\n"
set html to html plus "let i=0,playing=true,timer=null;\n"
set html to html plus "function draw(){\n"
set html to html plus "g.clearRect(0,0,420,420);\n"
set html to html plus "g.strokeStyle='#475569';g.beginPath();g.moveTo(20,300);g.lineTo(400,300);g.stroke();\n"
set html to html plus "g.fillStyle='#334155';g.fillRect(20,300,380,10);\n"
set html to html plus "for(let k=0;k<i;k++){const y=ys[k];const sy=Math.min(295,190-y*40);g.fillStyle='rgba(56,189,248,.18)';g.beginPath();g.arc(210,sy,12,0,7);g.fill();}\n"
set html to html plus "const y=ys[Math.min(i,ys.length-1)];const sy=Math.min(295,190-y*40);\n"
set html to html plus "g.fillStyle='#38bdf8';g.beginPath();g.arc(210,sy,12,0,7);g.fill();\n"
set html to html plus "g.strokeStyle='#bae6fd';g.stroke();\n"
set html to html plus "out.textContent='step '+(i+1)+' / '+ys.length+'   position y = '+y.toFixed(6);\n"
set html to html plus "i++;if(i>=ys.length){i=0;}\n"
set html to html plus "}\n"
set html to html plus "function tick(){if(playing){draw();}timer=setTimeout(tick,40);}\n"
set html to html plus "document.getElementById('play').onclick=()=>{playing=!playing;document.getElementById('play').textContent=playing?'Pause':'Play';};\n"
set html to html plus "document.getElementById('reset').onclick=()=>{i=0;draw();};\n"
set html to html plus "tick();\n"
set html to html plus "</script></body></html>\n"

call write text to with path = "physics.html", content = html
show "Wrote physics.html with " plus (call text of with value = (the length of ys)) plus " computed frames"
