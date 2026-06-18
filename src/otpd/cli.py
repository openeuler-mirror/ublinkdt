"""
Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved
[Software Name] is licensed under Mulan PSL v2.
You can use this software according to the terms and conditions of the Mulan PSL v2.
You may obtain a copy of Mulan PSL v2 at:
         http://license.coscl.org.cn/MulanPSL2
THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
See the Mulan PSL v2 for more details.
"""

import argparse
import sys
import logging

logger = logging.getLogger(__name__)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """Configure CLI logging with timestamp, level, logger name, and message."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(
        level=logging.WARNING,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )


def create_parser() -> argparse.ArgumentParser:
    """
    Create argument parser for otpd.

    Returns:
        ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog='ublinkdt',
        description='UBLink-DT (Unified Bus Link Diagnostic Tool)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  ublinkdt -m otpd -p 0 -c 0 --port-snr
  ublinkdt -m otpd -p 0 -c 0 -d 0 --stat
  ublinkdt -m otpd -p 0 -c 0 --optical
  ublinkdt -m otpd -p 0 -c 0 --ip --inet6
  ublinkdt -m otpd -p 0 -c 0 -d 0 --link-stat     """
    )

    parser.add_argument(
        '-m',
        type=str,
        dest='module',
        required=True,
        choices=['otpd'],
        help='Module to run (currently only: otpd)'
    )

    parser.add_argument(
        '-p',
        type=int,
        dest='port_id',
        required=False,
        help='Port ID (required, 0-8)'
    )

    parser.add_argument(
        '-d',
        type=int,
        dest='die_id',
        required=False,
        help='Die ID (required for --stat and --link-stat: 0 or 1; ignored by --port-snr and --optical)'
    )

    parser.add_argument(
        '-c',
        type=int,
        dest='chip_id',
        required=False,
        help='Chip ID (required, 0 or 1)'
    )

    parser.add_argument(
        '--port-snr',
        dest='port_snr',
        action='store_true',
        help='Query port SNR information'
    )

    parser.add_argument(
        '--stat',
        action='store_true',
        help='Query error codeword statistics'
    )

    parser.add_argument(
        '--optical',
        action='store_true',
        help='Query optical module information'
    )

    parser.add_argument(
        '--ip',
        action='store_true',
        help='Query IPv6 address for the port (requires --inet6)'
    )

    parser.add_argument(
        '--inet6',
        action='store_true',
        help='Use IPv6 (only with --ip)'
    )

    parser.add_argument(
        '--link-stat',
        dest='link_stat',
        action='store_true',
        help='Query link status information'
    )

    return parser


def validate_args(args: argparse.Namespace) -> bool:
    """
    Validate command-line arguments.

    Args:
        args: Parsed arguments

    Returns:
        True if valid, False otherwise
    """
    if args.port_id is None:
        print("Error: Port ID is required", file=sys.stderr)
        return False

    if args.chip_id is None:
        print("Error: Chip ID is required", file=sys.stderr)
        return False

    die_required = args.stat or args.link_stat
    if die_required and args.die_id is None:
        print("Error: Die ID is required", file=sys.stderr)
        return False

    if args.port_id < 0:
        print("Error: Port ID must be non-negative", file=sys.stderr)
        return False

    if args.chip_id not in (0, 1):
        print("Error: Chip ID must be 0 or 1", file=sys.stderr)
        return False

    if (args.stat or args.link_stat) and args.die_id not in (0, 1):
        print("Error: Die ID must be 0 or 1", file=sys.stderr)
        return False

    if not (args.port_snr or args.optical) and args.die_id is not None and args.die_id not in (0, 1):
        print("Error: Die ID must be 0 or 1", file=sys.stderr)
        return False

    if args.ip and not args.inet6:
        print("Error: --ip requires --inet6 (IPv4 queries are not supported)", file=sys.stderr)
        return False

    return True


def format_ublinkdt_command(args: argparse.Namespace, command_flag: str) -> str:
    """Return the concrete ublinkdt command represented by parsed args."""
    parts = [
        "ublinkdt", "-m", args.module,
        "-p", str(args.port_id),
        "-c", str(args.chip_id),
    ]
    if command_flag in ("--stat", "--optical", "--link-stat"):
        die_id = 3 if command_flag == "--optical" else args.die_id if args.die_id is not None else 0
        parts.extend(["-d", str(die_id)])
    if command_flag == "--ip":
        parts.append("--ip")
        if args.inet6:
            parts.append("--inet6")
    else:
        parts.append(command_flag)
    return " ".join(parts)


def run_with_query_context(args: argparse.Namespace, command_flag: str, callback):
    """Run a northbound query with its CLI command attached to diagnostics."""
    from .southbound import reset_query_context, set_query_context

    token = set_query_context(format_ublinkdt_command(args, command_flag))
    try:
        return callback()
    finally:
        reset_query_context(token)


def execute_commands(args: argparse.Namespace) -> int:
    """Execute the requested commands."""
    from .northbound import (
        get_port_snr, get_statistics, get_optical_info, get_link_status,
        get_ip_address,
    )

    commands_executed = False

    port_id = args.port_id
    chip_id = args.chip_id
    die_id = args.die_id if args.die_id is not None else 0

    def _run_subcommand(flag, callback, *, error_label, include_die=True,
                        allow_filenotfound=True, die_for_error=None):
        """Run one northbound subcommand, print its result, and return an rc.

        Returns 0 when a non-empty result was printed, 1 on failure (error to
        stderr). ``FileNotFoundError`` is mapped to an rc of 1 unless
        ``allow_filenotfound`` is False, in which case it re-raises (preserving
        the original behavior of the ``--ip`` path, which has no handler).
        """
        try:
            result = run_with_query_context(args, flag, callback)
        except FileNotFoundError as e:
            if allow_filenotfound:
                print(f"Error: Required command not found: {e}", file=sys.stderr)
                return 1
            raise
        if result:
            print(result)
            return 0
        if include_die:
            error_die_id = die_id if die_for_error is None else die_for_error
            print(
                f"Error: Failed to get {error_label} for port {port_id} "
                f"chip {chip_id} die {error_die_id}",
                file=sys.stderr,
            )
        else:
            print(
                f"Error: Failed to get {error_label} for port {port_id} "
                f"chip {chip_id}",
                file=sys.stderr,
            )
        return 1

    if args.port_snr:
        rc = _run_subcommand(
            "--port-snr", lambda: get_port_snr(port_id, chip_id, 0),
            error_label="port SNR", include_die=False,
        )
        if rc:
            return rc
        commands_executed = True

    if args.stat:
        rc = _run_subcommand(
            "--stat", lambda: get_statistics(port_id, chip_id, die_id),
            error_label="statistics",
        )
        if rc:
            return rc
        commands_executed = True

    if args.optical:
        rc = _run_subcommand(
            "--optical", lambda: get_optical_info(port_id, chip_id, 3),
            error_label="optical info", die_for_error=3,
        )
        if rc:
            return rc
        commands_executed = True

    if args.ip:
        rc = _run_subcommand(
            "--ip", lambda: get_ip_address(port_id, chip_id, args.inet6),
            error_label="IP address", include_die=False, allow_filenotfound=False,
        )
        if rc:
            return rc
        commands_executed = True

    if args.link_stat:
        rc = _run_subcommand(
            "--link-stat", lambda: get_link_status(port_id, chip_id, die_id),
            error_label="link status",
        )
        if rc:
            return rc
        commands_executed = True

    if not commands_executed:
        print("Error: No command specified. Use -h for help.", file=sys.stderr)
        return 1

    return 0


def main():
    """Main entry point for ublinkdt command."""
    configure_logging()
    parser = create_parser()
    args = parser.parse_args()

    if not validate_args(args):
        return 1

    return execute_commands(args)


if __name__ == '__main__':
    sys.exit(main())
