.. highlight:: rst

============================
Modbus weather
============================

-----------------
Running the app
-----------------

#. On your system, install `podman-docker` (or just the `docker`
  if it is the tool of your choice).

#. Build the image

    .. code-block:: bash

        docker build --target runner -t modbus_weather .

#. Run the program
    You will need the api_key.env or pass the API_KEY env variable or supply it on the command line.

    .. code-block:: bash
        docker run --env-file=./api_key.env modbus_weather

---------------
# Run the tests
---------------
    .. code-block:: bash

        docker build --target builder -t modbus_weather:dev .
        docker run modbus_weather:dev

---------------------
# Debug in container
--------------------
    .. code-block:: bash

      docker run -it --entrypoint /bin/bash -v ../bash_history:/root/.bash_history:z -v .:/app:z modbus_weather:dev