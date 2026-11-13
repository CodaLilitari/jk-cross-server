# Stock profile provenance

This file records the recovered profile selection from the earlier prototype.
The original prototype's scratch files were lost before publication. The profile
data and chat lines here were reconstructed; they are not presented as a byte
recovery of the missing JSON file.

The recovery run read `misc/models.dat` again from the installed original JK
retail resource archive and verified the same SHA-256 as the earlier audit:

```text
b14aac1feed2ff56a37ab7303f8a2c814114e91f6caa120e97a1edd94f1c6cb1
```

The current measurement is recorded in `qa/bots-recovery-assets.json`. No
LucasArts game archives, skins, sounds, or disc images are included with the
profiles. The installed original game supplies those assets.

| Registry comment label | Model | Sound | Assigned bot persona |
|---|---|---|---|
| BobaFett | `kyh4.3do` | `kybobafett.snd` | Boba Fett |
| JanOrs | `kya10.3do` | `kyfemale.snd` | Jan Ors |
| Katarn | `ky.3do` | `ky.snd` | Kyle Katarn |
| Trooper | `kym13.3do` | `kytrooper.snd` | Stormtrooper |
| Bossk | `kyi14.3do` | `kybossk.snd` | Bossk |
| Greedo | `kya17.3do` | `kygreedo.snd` | Greedo |
| Sariss | `kya9.3do` | `kyfemale.snd` | Sariss |
| Yun | `kya18.3do` | `kyyun.snd` | Yun |

Localized display names can differ from registry comments. Assigning a persona
is a project choice. Character labels affect the visible name, skin, sound class,
and original occasional chat only. No combat advantage or extra Force ability
is attached to a persona.

All 128 lines in `profiles.json` were newly written for this recovery under the
repository's MIT license. They do not copy film/game dialogue or another bot
project's chat corpus. Stock asset names are references to user-provided game
assets; the MIT license does not relicense those assets or Star Wars marks.
