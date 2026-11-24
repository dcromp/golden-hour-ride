# Golden Hour Ride

A proof-of-concept indoor cycling ride that runs in the browser (Three.js, one `index.html`).

This is a fork of [jamiemarsland/golden-hour-ride](https://github.com/jamiemarsland/golden-hour-ride) that adds a loop
round Tiptree in Essex, ERG mode with structured workouts, and support for riding on an iPad.

## What this fork adds

- **Tiptree loop** (the default course): 14.6 km and 105 m of climbing, from Church Road in Tiptree out to Inworth and
  Messing, across towards Layer Marney Tower, and home down Newbridge Road. The ground is Environment Agency 1 m lidar;
  the road, the side roads and junctions around it, buildings, woods and hedges are from OpenStreetMap. OpenStreetMap
  has only some of the area's houses and hedges, so the villages are emptier than the real ones.
  `?course=leckhampton` and `?course=valley` open the original courses; the Course button cycles through all three.
- **ERG mode**: the Workout button. Set your FTP, then either hold a steady wattage or ride a structured workout
  (seven are built in, and Zwift `.zwo` workout files can be added). The trainer is sent FTMS "set target power", so it
  holds each target whatever your cadence; − and + nudge the target, and Pause, Skip step and End do what they say.
  During free-ride steps, a pause, or after the workout, the trainer goes back to following the road's gradient.
  With no trainer connected the targets drive the ride on their own, so a workout can be tried at a desk.
- **Cadence** on screen, read from the trainer's power service.
- **iPad**: the screen is kept awake, buttons are larger on touch screens, and the trainer code works in Bluefy.

## Riding on an iPad with a Wahoo KICKR CORE 2

Safari on iPad (and Chrome on iPad, which is Safari underneath) has no Web Bluetooth, so the page cannot reach a trainer
from them. Use the free **Bluefy** browser from the App Store, which adds it:

1. The page has to be served over https (GitHub Pages does this). Open its address in Bluefy.
2. Close Zwift, the Wahoo app and anything else that might be holding the trainer's Bluetooth connection.
3. Pedal to wake the trainer, tap **Connect trainer** and pick the KICKR CORE. The button should read
   "Trainer: power and gradient".
4. Tap **Workout**, set your FTP, and pick a workout.

Zwift Cog: in ERG mode the trainer sets the resistance, so the single cog needs no shifting. Outside ERG mode there is
no virtual shifting here (that is Zwift's own protocol); the Hills − and + buttons are the nearest thing to changing gear.
The Zwift Click controller is not used: it speaks Zwift's own protocol too. Everything it would do is on screen.

## What's in it

- Three courses: the Tiptree loop above, an invented mountain valley, and a real 11.9 km Leckhampton loop built from Environment Agency lidar, dressed as the 19th-century hill (sheep, hay stooks, quarry smoke).
- Four looks: Golden, Overcast, Rain and Mist. Buttons at the top, keys 1–4, or by voice.
- Skip forward and back 250 m with the arrow keys.
- Hide everything on screen for a clean view: the Hide info button, the H key, or say "hide". Press H, click, or say "show" to bring it back.
- Power from a slider, or from a Bluetooth trainer (Chrome or Edge). If the trainer supports resistance control (FTMS), the ride also sends it the road gradient, so climbs feel harder; the button shows "Trainer: power and gradient" or "Trainer: power only". The trainer feels half the road gradient by default; the − and + buttons beside the trainer button change that in steps of 10 %, from off to the full gradient, and the choice is kept in the browser (`?hills=` sets it for one visit). With voice on, say "easier" or "harder" to move it by 20 %, "flat" for off, or "full" for all of it. The last trainer is remembered: the button reads "Reconnect trainer" and rejoins it without the browser's device list where Chrome allows that, and a dropped connection is retried automatically.
- Descents count half in the speed model and the rider brakes above 54 km/h, so downhill speed stays sensible.

## Run it locally

```bash
python3 -m http.server 8791
```

Then open http://localhost:8791/.

## Layout

- `index.html` – the whole ride.
- `assets/` – textures and course data. `textures.js` is an embedded copy of the textures, used only when the page is opened straight from disk.
- `tools/` – scripts that build the course data. To add a loop of your own, add its waypoints to `COURSES` in `tools/build_course.py`, run `python3 tools/build_course.py <name>` then `python3 tools/build_course_osm.py <name>`, and add it to `COURSES` near the top of the script in `index.html`.
- `deploy.sh` – publishes to Spacefast.

## Credits

- Textures: Poly Haven (CC0).
- Terrain: Environment Agency LiDAR Composite DTM, Open Government Licence v3.0.
- Roads, woodland and field boundaries: © OpenStreetMap contributors, ODbL.
- 3D engine: Three.js (MIT), loaded from jsDelivr.

## Licence

The code is released under the MIT licence: see `LICENSE`. Use it, change it, build your own ride.

The MIT licence covers the code only. The course data in `assets/leckhampton.js`, `assets/leckhampton_osm.js`, `assets/tiptree.js` and `assets/tiptree_osm.js` is derived from the sources credited above and stays under their terms: the Open Government Licence v3.0 for the terrain and the ODbL for the OpenStreetMap data. If you share or adapt that data, keep those credits.
