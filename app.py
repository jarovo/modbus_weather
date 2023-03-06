#!/usr/bin/env python3
import argparse
import asyncio
import logging
import requests
from operator import itemgetter

from server_async import run_async_server, setup_server
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder, BinaryPayloadBuilder

_logger = logging.getLogger()

OPENWEATHERMAP_API = "https://api.openweathermap.org/data/2.5/weather?"


def make_args_parser():
    parser = argparse.ArgumentParser(description="OpenWeatherAPI to modbus adapter.")
    parser.add_argument("api_key", help="Openweather API key.")
    parser.add_argument(
        "--log",
        default="info",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Log level",
    )
    parser.add_argument(
        "--modbus-listen-addres",
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
    return parser


getters = {
    "main": ("temp", "pressure", "humidity"),
    "wind": ("speed", "deg", "gust"),
    "clouds": ("all",),
    "sys": ("sunrise", "sunset"),
}


def get_lat_lon():
    return 49.5938, 17.2509


def make_openweathermap_request(args):
    lat, lon = get_lat_lon()
    resp = requests.get(
        OPENWEATHERMAP_API, params=dict(lat=lat, lon=lon, appid=args.api_key)
    ).json()
    _logger.debug(f"openweatherapi response: {resp}")
    return resp


def friendly_itemgetter(*items):
    if len(items) == 1:
        item = items[0]

        def g(obj):
            try:
                return obj[item]
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
    try:
        return tuple(*items)
    except TypeError:
        # The items is not an iterable.
        return tuple(
            items,
        )


def extract_vals(resp):
    vals = []
    for key, items in getters.items():
        _logger.debug(f"{key}, {items}")
        vals.extend(tuplify(friendly_itemgetter(*items)(resp[key])))
    _logger.debug(f"values: {vals}")
    return vals


async def get_weather_values(args):
    return extract_vals(make_openweathermap_request(args))


def convert_ints_to_floats(vals):
    builder = BinaryPayloadBuilder()
    for v in vals:
        builder.add_32bit_float(v)
    return builder.to_registers()


async def updating_task(args):
    """Run every so often,

    and updates live values of the context. It should be noted
    that there is a lrace condition for the update.
    """
    while True:
        _logger.debug("updating the context")
        fc_as_hex = 3
        slave_id = 0x00
        address = 0x10
        # values = context[slave_id].getValues(fc_as_hex, address, count=3)
        openweather_api_vals = await get_weather_values(args)
        values = convert_ints_to_floats(openweather_api_vals)
        txt = f"new values: {str(values)}"
        _logger.debug(txt)
        args.context[slave_id].setValues(fc_as_hex, address, values)
        await asyncio.sleep(60)


def setup_updating_server(args):
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


async def run_updating_server(args):
    """Start updater task and async server."""
    asyncio.create_task(updating_task(args))
    await run_async_server(args)


if __name__ == "__main__":
    parser = make_args_parser()
    cmd_args = parser.parse_args()
    cmd_args.comm = "tcp"
    cmd_args.framer = None
    run_args = setup_updating_server(cmd_args)
    asyncio.run(run_updating_server(run_args), debug=True)
