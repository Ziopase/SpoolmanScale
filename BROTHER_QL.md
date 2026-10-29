# Brother QL (network) printing

The scale can print its labels on a Brother QL over the network instead of
Bluetooth. Pick **Brother QL-700** under Printer in the web interface, type the
IPv4 address and press "Use as printer". Stock: 62 mm continuous tape
(DK-22205), cut to 62 x 30 mm.

The scale sends the QL raster protocol (the bytes `brother_ql` writes, checked
by `test/test_brother_ql.py`) to TCP port 9100. Nothing is read back: a job is
"sent", not "printed".

## QL-700 (USB only)

The QL-700 has no network port. Plug it into a Raspberry Pi (or any Linux box)
and let the Pi forward the socket to the USB device:

    sudo apt install socat
    ls /dev/usb/lp0                      # the printer, once it is plugged in and on

    # /etc/systemd/system/ql-bridge.service
    [Unit]
    Description=Brother QL TCP to USB
    After=network.target

    [Service]
    ExecStart=/usr/bin/socat TCP-LISTEN:9100,fork,reuseaddr FILE:/dev/usb/lp0
    Restart=always

    [Install]
    WantedBy=multi-user.target

    sudo systemctl enable --now ql-bridge

The QL-700 has an "Editor Lite" switch on the front; it must be **off** (green
light off), or the printer shows up as a USB stick and not as a printer.

Test without the scale: `printf '\x1b@' | nc <pi-ip> 9100` must not error.

## Network QLs (QL-710W, 720NW, 810W, 820NWB)

They listen on port 9100 themselves: type the printer's own address.
The QL-8xx take the same uncompressed raster; only the QL-700 was the target
here, the others are untested.

## Limits

- IPv4 address only, no host names.
- Only 62 mm continuous tape. The head prints 696 of its 720 dots: the label's
  outer 12 dots on each side fall off the tape (1 mm).
- Set on the web page only; the touchscreen shows the printer but cannot type
  an address.
- Not yet printed on real hardware.
