import asyncio
import pytest
import socket
import logging
import json
import datetime
from copy import deepcopy

import modbus_weather
from pymodbus.client import AsyncModbusTcpClient

from argparse import Namespace

OPENWEATHERMAP_DATA = {
    "lat": 49.5938,
    "lon": 17.2509,
    "timezone": "Europe/Prague",
    "timezone_offset": 7200,
    "current": {
        "dt": 1690740521,
        "sunrise": 1690687098,
        "sunset": 1690742183,
        "temp": 293.59,
        "feels_like": 294.07,
        "pressure": 1012,
        "humidity": 91,
        "dew_point": 292.07,
        "uvi": 0,
        "clouds": 73,
        "visibility": 10000,
        "wind_speed": 2.13,
        "wind_deg": 160,
        "wind_gust": 2.26,
        "weather": [
            {"id": 803, "main": "Clouds", "description": "broken clouds", "icon": "04d"}
        ],
    },
}


async def _async_wait_for_server(event_loop, host, port):
    while True:
        a_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            await event_loop.sock_connect(a_socket, (host, port))
            return
        except ConnectionRefusedError:
            await asyncio.sleep(0.01)

        finally:
            a_socket.close()


@pytest.fixture()
def server(event_loop, mocker):
    mocker.patch("modbus_weather.app.do_openweathermap_request")
    mocker.patch("modbus_weather.app.get_current_time")

    modbus_weather.app.get_current_time.return_value = datetime.datetime(
        1970, 1, 1, tzinfo=datetime.timezone.utc
    )
    modbus_weather.app.do_openweathermap_request.return_value = OPENWEATHERMAP_DATA

    cmd_args = Namespace()
    cmd_args.host = "localhost"
    cmd_args.port = 502
    cmd_args.log_level = "DEBUG"

    cmd_args.api_query_period = 30
    cmd_args.modbus_slave_id = 3
    cmd_args.api_key = "MOCK_API_KEY"
    run_args = modbus_weather.app.complete_updating_tcp_async_server(cmd_args)

    cancel_handle = asyncio.ensure_future(
        modbus_weather.app.start_updating_server(run_args), loop=event_loop
    )
    event_loop.run_until_complete(
        asyncio.wait_for(
            _async_wait_for_server(event_loop, cmd_args.host, cmd_args.port), 5.0
        )
    )

    try:
        yield cmd_args
    finally:
        cancel_handle.cancel()


@pytest.mark.asyncio
async def test_e2e_logic(mocker, server):
    client = AsyncModbusTcpClient("localhost")

    await client.connect()
    response = await client.read_holding_registers(0x10, 24)
    assert response.registers == [
        0,
        2,
        0,
        0,
        0,
        0,
        37443,
        34251,
        32068,
        0,
        46658,
        0,
        2112,
        60497,
        8259,
        0,
        4160,
        55203,
        37442,
        0,
        51534,
        44427,
        51534,
        23437,
    ]
    server.keep_running = False
    await client.close()
