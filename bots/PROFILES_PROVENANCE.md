# Stock profile provenance

This file records the recovered profile selection from the earlier prototype.
The original prototype's scratch files were lost before publication. The profile
data and chat lines here were reconstructed; they are not presented as a byte
recovery of the missing JSON file.

The earlier investigation read the original JK retail multiplayer skin registry
`models.dat` and recorded its SHA-256 as:

```text
b14aac1feed2ff56a37ab7303f8a2c814114e91f6caa120e97a1edd94f1c6cb1
```

That is historical evidence retained in the recovery record. It is not a new
hash measurement of game data distributed with this repository. No LucasArts
game archives, skins, sounds, or disc images are included with the profiles.
The installed original game supplies those assets.

| Retail menu entry | Model | Sound | Assigned bot persona |
|---|---|---|---|
| Mandalor | `kyh4.3do` | `kybobafett.snd` | Boba Fett |
| JanOrs | `kya10.3do` | `kyfemale.snd` | Jan Ors |
| Katarn | `ky.3do` | `ky.snd` | Kyle Katarn |
| Trooper | `kym13.3do` | `kytrooper.snd` | Stormtrooper |
| Trando | `kyi14.3do` | `kybossk.snd` | Bossk |
| Rodian | `kya17.3do` | `kygreedo.snd` | Greedo |
| Sariss | `kya9.3do` | `kyfemale.snd` | Sariss |
| Yun | `kya18.3do` | `kyyun.snd` | Yun |

Some menu labels describe a species or armor type. Assigning a named persona is
a project choice, not an assertion that the retail menu named every entry after
that character. Character labels affect the visible name, skin, sound class,
and original occasional chat only. No combat advantage or extra Force ability
is attached to a persona.

All 128 lines in `profiles.json` were newly written for this recovery under the
repository's MIT license. They do not copy film/game dialogue or another bot
project's chat corpus. Stock asset names are references to user-provided game
assets; the MIT license does not relicense those assets or Star Wars marks.
