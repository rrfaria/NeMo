# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
# Copyright 2015 and onwards Google, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from nemo_text_processing.inverse_text_normalization.es.graph_utils import (
    NEMO_DIGIT,
    GraphFst,
    delete_extra_space,
    delete_space,
)
from nemo_text_processing.inverse_text_normalization.es.utils import get_abs_path

try:
    import pynini
    from pynini.lib import pynutil

    PYNINI_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    PYNINI_AVAILABLE = False


def get_quantity(decimal: 'pynini.FstLike', cardinal_up_to_hundred: 'pynini.FstLike') -> 'pynini.FstLike':
    """
    Returns FST that transforms either a cardinal or decimal followed by a quantity into a numeral,
    e.g. one million -> integer_part: "1" quantity: "million"
    e.g. one point five million -> integer_part: "1" fractional_part: "5" quantity: "million"

    Args: 
        decimal: decimal FST
        cardinal_up_to_hundred: cardinal FST
    """
    numbers = cardinal_up_to_hundred @ (
        pynutil.delete(pynini.closure("0")) + pynini.difference(NEMO_DIGIT, "0") + pynini.closure(NEMO_DIGIT)
    )

    suffix = pynini.union(
        "millón",
        "millones",
        "millardo",
        "millardos",
        "billón",
        "billones",
        "trillón",
        "trillones",
        "cuatrillón",
        "cuatrillones",
    )
    res = (
        pynutil.insert("integer_part: \"")
        + numbers
        + pynutil.insert("\"")
        + delete_extra_space
        + pynutil.insert("quantity: \"")
        + suffix
        + pynutil.insert("\"")
    )
    res |= decimal + delete_extra_space + pynutil.insert("quantity: \"") + (suffix | "thousand") + pynutil.insert("\"")
    return res


class DecimalFst(GraphFst):
    """
    Finite state transducer for classifying decimal
        Decimal point is either "." or ",", determined by whether "punto" or "coma" is spoken.
            e.g. menos uno coma dos seis -> decimal { negative: "true" integer_part: "1" morphosyntactic_features: "," fractional_part: "26" }
            e.g. menos uno punto dos seis -> decimal { negative: "true" integer_part: "1" morphosyntactic_features: "." fractional_part: "26" }
        Also writes large numbers in shortened form, e.g. 
            e.g. uno coma dos seis millón -> decimal { negative: "true" integer_part: "1" morphosyntactic_features: "," fractional_part: "26" quantity: "millón" }
            e.g. dos millones -> decimal { negative: "true" integer_part: "2" quantity: "millones" }
    Args:
        cardinal: CardinalFst

    """

    def __init__(self, cardinal: GraphFst):
        super().__init__(name="decimal", kind="classify")

        cardinal_graph = cardinal.graph_no_exception | pynini.string_file(get_abs_path("data/numbers/es/zero.tsv"))

        graph_decimal = pynini.string_file(get_abs_path("data/numbers/digit.tsv"))
        graph_decimal |= pynini.string_file(get_abs_path("data/numbers/zero.tsv"))

        graph_decimal = pynini.closure(graph_decimal + delete_space) + graph_decimal
        graph_decimal |= cardinal_graph
        self.graph = graph_decimal

        decimal_point = pynini.cross("coma", "morphosyntactic_features: \",\"")
        decimal_point |= pynini.cross("punto", "morphosyntactic_features: \".\"")

        optional_graph_negative = pynini.closure(
            pynutil.insert("negative: ") + pynini.cross("menos", "\"true\"") + delete_extra_space, 0, 1
        )

        graph_fractional = pynutil.insert("fractional_part: \"") + graph_decimal + pynutil.insert("\"")
        graph_integer = pynutil.insert("integer_part: \"") + cardinal_graph + pynutil.insert("\"")
        final_graph_wo_sign = (
            pynini.closure(graph_integer + delete_extra_space, 0, 1)
            + decimal_point
            + delete_extra_space
            + graph_fractional
        )
        final_graph = optional_graph_negative + final_graph_wo_sign

        self.final_graph_wo_negative = final_graph_wo_sign | get_quantity(
            final_graph_wo_sign, cardinal.graph_hundred_component_at_least_one_none_zero_digit
        )
        final_graph |= optional_graph_negative + get_quantity(
            final_graph_wo_sign, cardinal.graph_hundred_component_at_least_one_none_zero_digit
        )
        final_graph = self.add_tokens(final_graph)
        self.fst = final_graph.optimize()
