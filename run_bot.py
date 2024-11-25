from highrise.__main__ import *
import asyncio
from config import *

async def start_bot():

    bot_file_name = "main"
    bot_class_name = "Bot"
    room_id = authorization.room
    bot_token = authorization.token

    my_bot = BotDefinition(getattr(import_module(bot_file_name), bot_class_name)(), room_id, bot_token)

    definitions = [my_bot]

    try:
        await main(definitions)  # Call main() directly with definitions

    except KeyboardInterrupt:
        print("Keyboard interrupt received. Restarting in new room...")
        await asyncio.sleep(2)

    except ConnectionResetError:
        print("Caught 'Cannot write to closing transport' error. Calling start_bot().")
        # Call your function when the error is caught

async def bot_run():
    while True:
        try:
            await start_bot()
        except (ConnectionResetError, WSServerHandshakeError, TimeoutError, TypeError):
            print("Attepmting to reconnect in 5 seconds...")
            await sleep(5)
            continue


# Check if the current module is the main module
if __name__ == "__main__":
    # Create an event loop
    loop = asyncio.get_event_loop()
    # Create a task within the event loop
    task = loop.create_task(bot_run())
    # Run the event loop until the task is complete
    loop.run_until_complete(task)
