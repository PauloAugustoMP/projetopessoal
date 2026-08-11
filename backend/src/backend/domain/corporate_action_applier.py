from .entities import CorporateAction, Position


class UnsupportedCorporateActionError(Exception):
    def __init__(self, type_: str) -> None:
        super().__init__(
            f'Corporate action of type "{type_}" is not applied to the position automatically '
            "-- see docs/business-rules.md section 5."
        )


def apply_corporate_action(position: Position, action: CorporateAction) -> Position:
    """Applies a split, reverse split, or bonus share event to a position, preserving the
    total amount invested (docs/business-rules.md section 5). Subscription rights are not
    supported here -- they must be recorded as a regular buy transaction once exercised.
    """
    if position.quantity == 0:
        return position

    if action.type in ("split", "reverse_split"):
        new_quantity = position.quantity * action.factor
        return Position(
            ticker=position.ticker,
            quantity=new_quantity,
            average_price=position.average_price / action.factor,
        )

    if action.type == "bonus_shares":
        total_cost = position.quantity * position.average_price
        new_quantity = position.quantity * (1 + action.factor)
        return Position(
            ticker=position.ticker,
            quantity=new_quantity,
            average_price=total_cost / new_quantity,
        )

    raise UnsupportedCorporateActionError(action.type)
