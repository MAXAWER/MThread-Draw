# Security

## What this program can do

MThread Draw drives a phone you have already unlocked and authorised over ADB.
Anything it can do, `adb` can do: it taps, swipes, reads the screen and pushes a
small jar to `/data/local/tmp`. It does not root anything, install an
application, or ask for a password.

It talks to nothing on the internet except when you ask for the optional neural
tracer, which downloads a model once from Hugging Face and caches it.

## Reporting something

Open a [security advisory](https://github.com/MAXAWER/MThread-Draw/security/advisories/new),
or an ordinary issue if it is not sensitive. There is no bounty; there is an
answer.

Worth reporting: anything that lets this run code you did not ask for, anything
that sends data off the machine, and anything in the bundled `adb` handling that
would let a hostile device or a hostile file take over the host.

Not worth reporting: that ADB itself grants broad control of a device. That is
what ADB is, and it is why the phone asks you to confirm the connection.

## Supported versions

The latest release. This is one person's project; there is no long-term support
branch, and a fix goes into the next release rather than being backported.
