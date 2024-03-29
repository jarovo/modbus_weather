#!/usr/bin/env python3
import os
import argparse
import asyncio
import logging
import requests
from operator import itemgetter
from datetime import datetime, timezone


from .server_async import run_async_server, setup_server
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder, BinaryPayloadBuilder

_logger = logging.getLogger


OPENWEATHERMAP_API = "https://api.openweathermap.org/data/3.0/onecall?"


def get_version():
    return 0, 1


class EnvDefault(argparse.Action):
    def __init__(self, envvar, required=True, default=None, **kwargs):
        if not default and envvar:
            if envvar in os.environ:
                default = os.environ[envvar]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(default=default, required=required, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


def make_args_parser():
    parser = argparse.ArgumentParser(description="OpenWeatherAPI to modbus adapter.")
    parser.add_argument(
        "api_key", action=EnvDefault, envvar="API_KEY", help="Openweather API key."
    )
    parser.add_argument(
        "--api-query-period",
        default=5 * 60,
        type=float,
        help="Openweather API request period.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Log level",
    )
    parser.add_argument(
        "--modbus-listen-address",
        dest="address",
        default="0.0.0.0",
        help="Address for the Modbus slave (server) to listen on.",
    )
    parser.add_argument(
        "--modbus-listen-port",
        dest="port",
        default="502",
        help="Modbus slave (server) port.",
    )
    parser.add_argument(
        "--modbus-slave-id",
        type=int,
        help="Modbus slave id.",
    )
    return parser


getters = {
    "main": ("temp", "pressure", "humidity"),
    "wind": ("speed", "deg", "gust"),
    "clouds": ("all",),
    "sys": ("sunrise", "sunset"),
}


def get_current_time():
    return datetime.now()


def get_lat_lon():
    return 49.5938, 17.2509


def do_openweathermap_request(args):
    lat, lon = get_lat_lon()
    resp = requests.get(
        OPENWEATHERMAP_API,
        params=dict(
            lat=lat, lon=lon, appid=args.api_key, exclude="minutely,hourly,daily,alerts"
        ),
    ).json()
    _logger().debug(f"openweatherapi response: {resp}")
    return resp


def friendly_itemgetter(*items):
    """
    Contrary to the operator.itemgetter this one is more verbose in the error
    messages when an item is missing.

    >>> my_dict = dict(foo = "baz1", bar = "baz2")

    >>> friendly_itemgetter("foo")(my_dict)
    'baz1'
    >>> friendly_itemgetter("foo", "bar")(my_dict)
    ('baz1', 'baz2')
    >>> friendly_itemgetter("bar", "foo")(my_dict)
    ('baz2', 'baz1')
    """
    if len(items) == 1:
        item_name = items[0]

        def g(obj):
            try:
                return obj[item_name]
            except KeyError as exc:
                raise KeyError(f"{exc} when processing {obj}")

    else:
        try:

            def g(obj):
                return tuple(obj[item] for item in items)

        except KeyError as exc:
            raise Exception(f"{exc.msg} when processing {obj}")

    return g


def tuplify(*items):
    """
    When given a singleton object, return tuple. This is in
    contrast with the builtin tuple().

    >>> tuple(object())
    Traceback (most recent call last):
        ...
    TypeError: 'object' object is not iterable

    >>> tuplify(object())
    (<object ...>,)
    """
    try:
        return tuple(*items)
    except TypeError:
        # The items is not an iterable.
        return tuple(
            items,
        )


def extract_vals(resp):
    current = resp["current"]
    vals = [
        current["temp"],
        current["pressure"],
        current["humidity"],
        current["wind_speed"],
        current["wind_deg"],
        current["wind_gust"],
        current["clouds"],
        current["sunrise"],
        current["sunset"],
    ]
    return vals


async def get_weather_values(args):
    vals = extract_vals(do_openweathermap_request(args))
    return vals


def convert_to_32bit_float_registers(vals):
    builder = BinaryPayloadBuilder()
    for v in vals:
        builder.add_32bit_float(v)
    return builder.to_registers()


def convert_to_64bit_float_registers(vals):
    builder = BinaryPayloadBuilder()
    for v in vals:
        builder.add_64bit_float(v)
    return builder.to_registers()


async def updating_task(args):
    """Run every so often,

    and updates live values of the context. It should be noted
    that there is a lrace condition for the update.
    """
    while args.keep_running:
        try:
            _logger().debug("updating the context")
            fc_as_hex = 3
            slave_id = args.modbus_slave_id
            address = 0x10

            # values = context[slave_id].getValues(fc_as_hex, address, count=3)
            openweather_api_vals = await get_weather_values(args)

            dt = get_current_time()
            timestamp = dt.replace(tzinfo=timezone.utc).timestamp()
            _logger().debug(f"timestamp: {timestamp}")

            values = []
            values.extend(get_version())
            values.extend(convert_to_64bit_float_registers((timestamp,)))
            values.extend(convert_to_32bit_float_registers(openweather_api_vals))

            printout = list(f"{v:b}" for v in values)
            _logger().debug(f"New values: {str(values)}")
            _logger().debug(f"New values: {printout}")

            args.context[slave_id].setValues(fc_as_hex, address, values)
        except Exception as exc:
            _logger().exception("Exception happened when updating the values.")
        finally:
            await asyncio.sleep(args.api_query_period)


def setup_updating_server_args(args):
    """Run server setup."""
    # The datastores only respond to the addresses that are initialized
    # If you initialize a DataBlock to addresses of 0x00 to 0xFF, a request to
    # 0x100 will respond with an invalid address exception.
    # This is because many devices exhibit this kind of behavior (but not all)

    # Continuing, use a sequential block without gaps.
    datablock = ModbusSequentialDataBlock(0x00, [0] * 100)
    context = ModbusSlaveContext(
        di=datablock, co=datablock, hr=datablock, ir=datablock, unit=1
    )
    args.context = ModbusServerContext(slaves=context, single=True)
    return setup_server(args)


async def start_updating_server(args):
    """Start updater task and async server."""
    asyncio.create_task(updating_task(args))
    return await run_async_server(args)


def complete_updating_tcp_async_server(cmd_args):
    cmd_args.comm = "tcp"
    cmd_args.framer = None
    cmd_args.keep_running = True

    set_logger(cmd_args)

    run_args = setup_updating_server_args(cmd_args)
    return run_args


def set_logger(cmd_args):
    logging.basicConfig(level=get_log_level(cmd_args))


def get_log_level(cmd_args):
    return cmd_args.log_level.upper()


def main():
    parser = make_args_parser()
    cmd_args = parser.parse_args()
    run_args = complete_updating_tcp_async_server(cmd_args)
    asyncio.run(
        start_updating_server(run_args), debug=("DEBUG" == get_log_level(cmd_args))
    )
