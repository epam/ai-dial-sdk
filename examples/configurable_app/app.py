"""
A DIAL application that is configurable by the user.
"""

import random

import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.chat_completion.form import (
    Button,
    ButtonField,
    FormMetaclass,
    form,
)
from aidial_sdk.deployment.configuration import (
    ConfigurationRequest,
    ConfigurationResponse,
)
from aidial_sdk.pydantic_v1 import BaseModel, Field
from examples.configurable_app.game import GameState, Move, Player


# The start configuration sets up the configuration for the whole conversation.
# In this case, the user can select the player for the tic-tac-toe game.
#   - The configuration class must inherit from Pydantic `BaseModel`.
#   - `DialFormMetaclass` is a required metaclass that enables `buttons` field in the Field descriptor.
class InitConfiguration(BaseModel, metaclass=FormMetaclass):
    # The flag disable the chat message input field.
    # By doing so we force the user to interact with the buttons.
    _dial_chatMessageInputDisabled = True

    player: Player = Field(
        description="Select tic-tac-toe player",
        # buttons field accepts a list of Button objects with the following properties:
        # * submit (bool): Whether the button should submit the whole form on click.
        # * title (str): The caption text displayed on the button.
        # * const (str): The value that will be submitted if the button is clicked.
        # * confirmationMessage (str): The message that will be displayed to the user before submitting the form in a confirmation dialog.
        buttons=[
            Button(
                const="X",
                submit=True,
                title="𝕏",
                confirmationMessage="Are you sure you want to play as 𝕏? It goes first.",
            ),
            Button(
                const="O",
                submit=True,
                title="Ⓞ",
                confirmationMessage="Are you sure you want to play as Ⓞ? It goes second.",
            ),
        ],
    )


# The move form defines the action of the user in the conversation.
# In particular the move one is making in the tic-tac-toe game encoded as a string: A1, B3 etc.
# Note that the form doesn't have any buttons, since the moves are determined dynamically.
# Later on we will add buttons to the model using a class decorator.
class MoveForm(BaseModel):
    move: str


# ChatCompletion is an abstract class for applications and model adapters
class ConfigurableApplication(ChatCompletion):

    async def configuration(
        self, request: ConfigurationRequest
    ) -> ConfigurationResponse:
        # Return the schema of the initial configuration
        return ConfigurationResponse(**InitConfiguration.schema())

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        # Retrieve the configuration from the request and parse it
        cf = request.custom_fields
        assert cf is not None and cf.configuration
        init_conf = InitConfiguration.parse_obj(cf.configuration)

        if len(request.messages) == 1:
            # The game just started. Init empty state.
            state = GameState()
        else:
            # Retrieving the game state from the last message state
            last_message = request.messages[-1]

            cc = last_message.custom_content
            assert (
                cc is not None
                and cc.state is not None
                and cc.form_value is not None
            )
            state = GameState.parse_obj(cc.state)

            # Update the game state with the last move from the user
            user_form = MoveForm.parse_obj(cc.form_value)
            user_move = Move.parse(user_form.move)
            state = state.make_move(user_move)

        if len(request.messages) == 1 and init_conf.player == "X":
            # X player always goes first, so
            # if the game just started and the user plays as X,
            # then skip the move by the bot.
            bot_response = "Make a move"
        else:
            # Otherwise, make a random move by the bot
            moves = state.possible_moves
            bot_move = random.choice(moves)
            state = state.make_move(bot_move)
            bot_response = (
                "I moved to " + bot_move.print() + ". Now it's your turn."
            )

        bot_response += "\n\n" + state.print()

        # Generate response with a single choice
        with response.create_single_choice() as choice:
            # Fill the content of the response from the bot
            choice.append_content(bot_response)

            # ... along with the request for the next move
            button_fields = [
                ButtonField(
                    name="move",
                    options=[
                        Button(
                            title=move.print(),
                            const=move.print(),
                            confirmationMessage="Are you sure you want to make this move?",
                            submit=True,
                        )
                        for move in state.possible_moves
                    ],
                )
            ]

            # Use the form decorator to add buttons to the form.
            # The form doesn't allow for an arbitrary user input,
            # but only actions via the buttons.
            form_cls = form(
                disable_chat_input=True,
                button_fields=button_fields,
            )(MoveForm)
            choice.set_form_schema(form_cls.schema())

            # Save the game state in the bot message
            choice.set_state(state.dict())


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_chat_completion("app", ConfigurableApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
