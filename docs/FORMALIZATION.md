# Formalization model

The production kernel checks one **concrete finite transition** at a time. It does not yet quantify over an abstract board map and derive every chess relation internally.

## Agent protocol

```litex
prop square(file, rank, index Z): ...
prop move(from_square, to_square Z): ...
prop promotion_choice(promotion Z): ...
prop result(status Z): ...
prop result_witness(status, checker_count, legal_reply_count Z): ...
```

The query creates local square/status aliases and checks a readable record such as:

```litex
by def $move(e2, e4)
by def $promotion_choice(0)
by def $result(ongoing)
by def $result_witness(ongoing, 0, 20)
```

## Movement layer

The kernel contains predicates for:

- pawn single/double moves, captures, promotion and en passant;
- knight, bishop, rook, queen and king geometry;
- four castling cases;
- path clearance, ownership and target occupancy.

`query.py` selects one predicate and supplies concrete integer parameters. An incorrect selection or parameter set is rejected by Litex.

## Sparse board layer

```litex
prop sparse_square_edit(index, before_piece, after_piece, weight, contribution Z): ...
prop sparse_board_transition(before_code, after_code,
    contribution1, contribution2, contribution3, contribution4,
    edit_count, duplicate_count, before_mismatch_count,
    after_mismatch_count Z): ...
```

For board square `i` with piece code `p_i in [-6,6]`:

```text
BoardCode(B) = Σ (p_i + 6) 16^i.
```

Because each digit lies in `0..12`, this is an exact injective base-16 representation. A move supplies two to four canonical edits and proves the code increment. It is not a Zobrist or cryptographic hash.

## Metadata layer

`metadata_transition` compares actual and independently expected values for:

- side to move;
- K/Q/k/q castling flags;
- en-passant file/rank;
- halfmove clock;
- fullmove number.

These values are deliberately outside `BoardCode`; identical piece placement can carry different legal histories.

## Safety and final contract

The query checks structural king counts, supplied attack counts, castling start/transit/destination safety and a final `legal_transition` zero-mismatch contract.

Attack enumeration and legal-move set generation are currently host-side computations. Litex checks the resulting concrete facts; this boundary is documented rather than hidden.
