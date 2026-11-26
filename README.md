# Lanternist Studio for TouchDesigner

A free component that connects TouchDesigner and Lanternist Studio. Drop it into any
TouchDesigner project, with any licence, the free Non-Commercial one included.

- **Send TouchDesigner to Studio.** Pick up to four TOPs. On the same computer they go over
  Spout, at full size and with no delay; across the network they go over NDI®. In Studio they
  appear in the Library's live inputs under *TouchDesigner*: drop one on a surface, or press
  **Show in Studio** and a surface showing it is made for you.
- **Studio's parameters in TouchDesigner, both ways.** Every parameter of the Studio project is
  on the *Studio parameters* page. Move one in TouchDesigner and Studio follows; change it in
  Studio (a cue, a fader, OSC) and TouchDesigner follows.
- **Run the show.** GO, BACK and *Go to cue* run Studio's cue list.
- **Studio's picture in TouchDesigner.** Share a Studio output over Spout or NDI and receive it
  here: the component's output connector carries it.

## Install

1. Download `lanternist_studio.tox`.
2. Drag it into your TouchDesigner project.

That's all: it finds Lanternist Studio on this computer or on the local network by itself. If
Studio is on another network, type its address on the *Studio* page.

## Use

**Studio page**
- *Status* says what it is connected to.
- *GO*, *BACK*, *Cue* and *Go to cue* run Studio's cue list.
- *Find Studio again* looks again (after Studio was restarted on another computer).

**Send to Studio page**
- *TOP 1 … TOP 4*: the TOPs to send; *Send TOP n* switches each on or off.
- *Send over*: Spout (this computer), NDI (the network) or both. If Spout cannot send with your
  licence, the TOPs go over NDI by themselves and *Status* says so.
- *Sender name*: what Studio lists them under (`TD - project - top` when empty).
- *Show in Studio*: a new surface in Studio for each TOP being sent (Studio on this computer).

**From Studio page**
- Switch on *Receive a Studio output*, choose Spout or NDI and type the name Studio sends under
  (in Studio: an output's *Share through Spout* or *Share through NDI®*; it sends as
  `Lanternist - <output name>`).

**Studio parameters page** appears once connected: Studio's project, parameter by parameter.

Keep TouchDesigner's window open (not minimised) while it sends: TouchDesigner pauses when it
is minimised.

## Running TouchDesigner components inside Studio

With a paid TouchDesigner licence (Commercial, Pro, Educational or TouchPlayer), Lanternist
Studio can also run a `.tox` itself: drop the file on a surface in Studio. Its parameters show
in Studio's inspector and can be driven by cues, the timeline, OSC and MIDI. This component is
for every other case, and for sending from a running TouchDesigner project.

## Requirements

- TouchDesigner 2023 or later, any licence.
- Lanternist Studio 1.0 or later.
- Windows. NDI needs nothing more: TouchDesigner and Studio both speak it.

## Licence

MIT, see [LICENSE](LICENSE).

NDI® is a registered trademark of Vizrt NDI AB. TouchDesigner is a product of Derivative Inc.;
this component is not made or endorsed by Derivative.
