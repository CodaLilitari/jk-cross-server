# Attribution and scope

JK Cross Server is new server integration work directed by Andrei and implemented by Lilitari, with parallel collaborators for the native engine, browser transport, and original retail runtime. These are contribution credits, not a claim to ownership of the original games or third-party code.

The native core derives from OpenJKDF2, including the OpenJKDF2-MotS-Fixes work credited to Andrei Kiralv/Darkahn and Coda Lilitari. The browser protocol and client are by Tristamus and other OpenJKDF2/JKDF2Web contributors. The Python asset adapter implements the existing maps.js/mods.js transfer, reference and fingerprint formats from the pinned published client source; the client is fetched separately without modification. Their existing author and license notices remain applicable.

The original Jedi Knight and Mysteries of the Sith game content and executables remain the property of their respective owners. Microsoft DirectPlay is an external runtime dependency. No license to those materials is granted by this project. The release excludes commercial game archives, retail executables, ISOs, and Microsoft runtime binaries.

New Python supervisor and transport-adapter code, original DirectPlay gateway code, and original build/test scripts are provided under the MIT license below unless an individual file specifies otherwise. Engine patches are governed by the engine's existing license. Bundled third-party libraries retain their own licenses; see native notices and licenses/.

The optional current JKWeb bot runtime uses a patched source build of Tristamus's
OpenJKDF2 `web-mp` branch. Its provenance is in `web_bots/BUILD.json`, with the
corresponding patch, application object files and libsmacker relink source in
`web_bots/`. Its upstream relay is fetched separately at a verified commit;
this repository does not relicense that author's relay. No private character
archive or original game asset is included in the bot runtime.
