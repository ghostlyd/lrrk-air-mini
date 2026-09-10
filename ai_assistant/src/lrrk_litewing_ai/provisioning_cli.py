"""Explicit local operator provisioning; no AI tool or automatic activation."""
import argparse
import secrets
from pathlib import Path

from .provisioning_bundle import save_pending, load_pending, BundleError
from .provisioning_serial import ProvisioningSerial, SerialProvisioningError
from .provisioning_transport import _exchange
from .usb_provisioning_wire import encode_config, submission
import time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='save fresh pending credentials, then submit once')
    create.add_argument('--directory', type=Path, required=True,
                        help='existing private 0700 directory outside Git')
    reconcile = commands.add_parser('reconcile', help='poll saved transaction; never retransmit')
    reconcile.add_argument('--bundle', type=Path, required=True)
    for command in (create, reconcile):
        command.add_argument('--device', required=True)
        command.add_argument('--location', required=True)
    args = parser.parse_args(argv)
    stream = None
    try:
        if args.command == 'create':
            transaction = secrets.token_bytes(16)
            blob = encode_config('LW-' + secrets.token_hex(4), secrets.token_urlsafe(24),
                                 secrets.token_bytes(32))
            save_pending(args.directory, transaction, blob)
            request = submission(transaction, blob)
        else:
            transaction, _ = load_pending(args.bundle)
            request = None
        stream = ProvisioningSerial(args.device, args.location, request=request)
        result = _exchange(stream, transaction, request, time.monotonic)
        stream.close()
        stream = None
    except (BundleError, SerialProvisioningError, OSError, ValueError):
        print('unresolved; preserve pending bundles; do not automatically retry')
        return 2
    finally:
        if stream is not None:
            try:
                stream.close()
            except SerialProvisioningError:
                pass  # already unresolved; no second device-close attempt internally
    print(result.outcome + '; pending bundle retained; activation not verified')
    return 0 if result.verified else 2


if __name__ == '__main__':
    raise SystemExit(main())
