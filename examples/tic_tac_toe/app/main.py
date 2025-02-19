"""
A DIAL application that is configurable by the user.
"""

import random
from typing import Optional

import uvicorn

from aidial_sdk import DIALApp
from aidial_sdk.chat_completion import ChatCompletion, Request, Response
from aidial_sdk.chat_completion.form import Button, FormMetaclass, form
from aidial_sdk.deployment.configuration import (
    ConfigurationRequest,
    ConfigurationResponse,
)
from aidial_sdk.pydantic_v1 import BaseModel, Field

from .game import O_PLAYER, X_PLAYER, Board, Move, Player
from .request import (
    get_configuration,
    get_message_form_value,
    get_message_state,
)


# The initial configuration sets up the tic-tac-toe game.
# The user can select the player: either X or O.
# The configuration class must inherit from Pydantic `BaseModel`.
# `FormMetaclass` is a required metaclass that enables `buttons` field in the Field descriptor as well as `Config` extensions.
class InitConfiguration(BaseModel, metaclass=FormMetaclass):
    # The flag disables the chat message input field.
    # This forces the user to interact with the buttons.
    class Config:
        chat_message_input_disabled = True

    player: Player = Field(
        description="Select tic-tac-toe player",
        # The 'buttons' parameter of the field descriptor accepts a list of Button objects with the following properties:
        # * submit (bool): Whether the button should submit the whole form on click.
        # * title (str): The caption text displayed on the button.
        # * const (int|float): The value that will be submitted when the button is clicked.
        # * confirmationMessage (str): The message that will be displayed to the user before submitting the form in a Yes/No confirmation dialog.
        buttons=[
            Button(
                const=X_PLAYER,
                submit=True,
                title="X",
                confirmationMessage="Are you sure you want to play as X? It goes first.",
            ),
            Button(
                const=O_PLAYER,
                submit=True,
                title="O",
                confirmationMessage="Are you sure you want to play as O? It goes second.",
            ),
        ],
    )


# The form defines the move the user in making during the tic-tac-toe game.
# The bot suggest a list of available moves to the user.
# The user pick one of the move by its index in the list and returns this data structure to the application.
# Note that the form doesn't have any buttons, since the moves are determined dynamically.
# The buttons are added to the model dynamically using the class decorator "form".
class MoveForm(BaseModel):
    class Config:
        chat_message_input_disabled = True

    move: int


class MoveOutcome(BaseModel):
    bot_response: str
    show_board: bool = True
    board: Board


# ChatCompletion is an abstract class for applications and model adapters
class TicTacToeApplication(ChatCompletion):

    async def configuration(
        self, request: ConfigurationRequest
    ) -> ConfigurationResponse:
        # Return the schema of the initial configuration
        return ConfigurationResponse(**InitConfiguration.schema())

    async def chat_completion(
        self, request: Request, response: Response
    ) -> None:
        # Retrieve the configuration from the request and parse it
        init_conf = InitConfiguration.parse_obj(get_configuration(request))
        user_player = init_conf.player

        if len(request.messages) == 1:
            # The game just started. Init empty board.
            board = Board()
            user_move = None
        else:
            # Retrieve the user move from the last user message
            if form_value := get_message_form_value(request.messages[-1]):
                user_form = MoveForm.parse_obj(form_value)
                user_move = Move.from_button_value(user_form.move)

            # Retrieve the game board from the last bot message
            state_dict = get_message_state(request.messages[-2])
            assert state_dict is not None
            board = Board.parse_obj(state_dict)

        # Make a move by the bot
        move_outcome = TicTacToeApplication.make_bot_move(
            board, user_player, user_move
        )

        # Generate response with a single choice
        with response.create_single_choice() as choice:
            board = move_outcome.board
            bot_response = move_outcome.bot_response

            if move_outcome.show_board:
                bot_response += "\n\n" + board.to_markdown()

            # Fill the content of the response from the bot
            choice.append_content(bot_response)

            if not board.finished:
                # Add the buttons if the game hasn't finished yet
                move_button = Field(
                    description="Available moves",
                    buttons=[
                        Button(
                            title=move.print(),
                            const=move.to_button_value(),
                            confirmationMessage="Are you sure you want to make this move?",
                            submit=True,
                        )
                        for move in board.possible_moves
                    ],
                )

                # Use the form decorator to add buttons to the form.
                # The form doesn't allow for an arbitrary user input,
                # but only actions via the buttons.
                _MoveForm = form(move=move_button)(MoveForm)
                choice.set_form_schema(_MoveForm.schema())

            # Save the game board in the bot message
            choice.set_state(board.dict())

    @staticmethod
    def make_bot_move(
        board: Board, user_player: Player, user_move: Optional[Move]
    ) -> MoveOutcome:
        """Helper function that advances the game board according to the bot and user moves."""

        bot_player = X_PLAYER if user_player == O_PLAYER else O_PLAYER

        if user_move is not None:
            if board.finished:
                # The game is finished, no need to continue
                return MoveOutcome(
                    bot_response="The game is already finished. Restart the conversation to play again.",
                    show_board=False,
                    board=board,
                )

            # Update the game board with the last move from the user
            board = board.make_move(user_move)

            if board.status == user_player:
                return MoveOutcome(
                    bot_response="You won! Congratulations! 🎉", board=board
                )

            if board.status == "Draw":
                return MoveOutcome(bot_response="It's a draw! 😐", board=board)

        if user_move is None and user_player == X_PLAYER:
            # X player always goes first, so
            # if the game just started and the user plays as X,
            # then skip the move by the bot.
            return MoveOutcome(
                bot_response="You go first. Make a move.", board=board
            )
        else:
            # Otherwise, make a random move by the bot
            moves = board.possible_moves
            bot_move = random.choice(moves)
            board = board.make_move(bot_move)
            bot_response = "I moved to " + bot_move.print() + ". "

            if board.status == bot_player:
                bot_response += "I won! 🎉"
            elif board.status == "Draw":
                bot_response += "It's a draw! 😐"
            else:
                bot_response += "Now it's your turn."

            return MoveOutcome(bot_response=bot_response, board=board)


# DIALApp extends FastAPI to provide a user-friendly interface for routing requests to your applications
app = DIALApp()
app.add_chat_completion("app", TicTacToeApplication())

# Run built app
if __name__ == "__main__":
    uvicorn.run(app, port=5000)
