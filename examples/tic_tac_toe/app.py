"""
A DIAL application that is configurable by the user.
"""

import random
from typing import Optional

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
from examples.tic_tac_toe.game import GameState, Move, Player
from examples.tic_tac_toe.request import (
    get_configuration,
    get_message_form_value,
    get_message_state,
)


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


class MoveOutcome(BaseModel):
    bot_response: str
    show_board: bool = True
    state: GameState


# ChatCompletion is an abstract class for applications and model adapters
class TicTacToeApplication(ChatCompletion):

    async def configuration(
        self, request: ConfigurationRequest
    ) -> ConfigurationResponse:
        # Return the schema of the initial configuration
        return ConfigurationResponse(**InitConfiguration.schema())

    @staticmethod
    def make_bot_move(
        init_conf: InitConfiguration,
        state: GameState,
        user_move: Optional[Move],
    ) -> MoveOutcome:
        user_player = init_conf.player
        bot_player = "X" if user_player == "O" else "O"

        if user_move is not None:
            if state.finished:
                # The game is finished, no need to continue
                return MoveOutcome(
                    bot_response="The game is already finished. Restart the conversation to play again.",
                    show_board=False,
                    state=state,
                )

            # Update the game state with the last move from the user
            state = state.make_move(user_move)

            if state.status == user_player:
                return MoveOutcome(
                    bot_response="You won! Congratulations! 🎉", state=state
                )

            if state.status == "Draw":
                return MoveOutcome(bot_response="It's a draw! 😐", state=state)

        if user_move is None and user_player == "X":
            # X player always goes first, so
            # if the game just started and the user plays as X,
            # then skip the move by the bot.
            return MoveOutcome(
                bot_response="You go first. Make a move.", state=state
            )
        else:
            # Otherwise, make a random move by the bot
            moves = state.possible_moves
            bot_move = random.choice(moves)
            state = state.make_move(bot_move)
            bot_response = "I moved to " + bot_move.print() + ". "

            if state.status == bot_player:
                bot_response += "I won! 🎉"
            elif state.status == "Draw":
                bot_response += "It's a draw! 😐"
            else:
                bot_response += "Now it's your turn."

            return MoveOutcome(bot_response=bot_response, state=state)

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        # Retrieve the configuration from the request and parse it
        init_conf = InitConfiguration.parse_obj(get_configuration(request))

        if len(request.messages) == 1:
            # The game just started. Init empty state.
            state = GameState()
            user_move = None
        else:
            # Retrieve the user move from the last user message
            if form_value := get_message_form_value(request.messages[-1]):
                user_form = MoveForm.parse_obj(form_value)
                user_move = Move.parse(user_form.move)

            # Retrieve the game state from the last bot message
            state_dict = get_message_state(request.messages[-2])
            assert state_dict is not None
            state = GameState.parse_obj(state_dict)

        # Make a move by the bot
        move_outcome = TicTacToeApplication.make_bot_move(
            init_conf, state, user_move
        )

        # Generate response with a single choice
        with response.create_single_choice() as choice:
            state = move_outcome.state
            bot_response = move_outcome.bot_response

            if move_outcome.show_board:
                bot_response += "\n\n" + state.print_board()

            # Fill the content of the response from the bot
            choice.append_content(bot_response)

            if not state.finished:
                # Added the buttons if the game hasn't finished yet
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
app.add_chat_completion("app", TicTacToeApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
