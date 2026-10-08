# Vasarely Room 6 Planner

A planning model of exhibition room 6 (E-102) of the Vasarely Museum, Budapest: 12.025 × 15.00 m, 178.95 m², ceiling at 329 cm.

**Open the planner:** https://herhu.github.io/vasarely-room6-planner/

## Web planner (`index.html`)

- **3D, Plan and Walk views.** Walk through the room at 160 cm eye height with W A S D.
- **Mobile walls.** Drag the white walls (MOB4, MOB2N, MOB2S) and rotate them with R. Clashes with pillars, benches, doors and other walls are flagged.
- **Artworks.** Add images (PNG, JPG, WebP…) one by one or in batches, or import an Excel/CSV list with titles and sizes. Drag artworks from the list onto any wall, move them, and resize them with the corner dot.
- **Room details from the elevation drawings.** Arched window niches with casements, arched doors (stone frame and double doors to room 5), display cases, and the two covered windows (east 3, west 2), which you can switch back on in the Walls tab. Every colour can be changed with a picker or a #hex code.
- **Frames from drawings.** One click places the empty frames and pink panels from the elevations, at their drawn positions.
- **Display cases.** Drag, rotate, resize, add or delete them (Walls tab).
- **Layouts.** Switch between the options in the drawings (4 m wall position, west-wall frame variants), save your own layouts, and download a layout file to send to someone. They load it in the Layouts tab or drop it on the page.
- **Measure.** Click any wall, window, pillar, artwork or the floor to see its size and distances.
- **Copy hanging list.** Copies a table you can paste into Excel.

Your layout and artworks are saved only in your own browser.

## Blender model

- `vasarely_room6.py` builds the room in Blender 4.2+ / 5.x and adds a "Kiállítás" panel (press N) for hanging artworks.
- `Vasarely_Terem6.blend` is the ready-made file with the script embedded.
- `sample_artworks.csv` is an example artwork list. It imports into both the Blender panel and the web planner.
