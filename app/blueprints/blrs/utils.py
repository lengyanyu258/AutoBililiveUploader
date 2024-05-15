import json
from collections import Counter
from enum import EnumMeta
from typing import IO, Any, Dict, List


def get_input_examples(
    fp: IO[Any], field_name: str, EventsEnum: EnumMeta
) -> Dict[str, Dict[str, Any]]:
    with fp:
        examples: List[Dict[str, Any]] = json.load(fp)

    input_examples: Dict[str, Dict[str, Any]] = {}
    event_type_counter = Counter()

    for example in examples:
        event_type_name: str = example[field_name]
        event_type_counter.update([event_type_name])
        example_number = event_type_counter[event_type_name]

        if example_number == 1:
            input_examples[event_type_name] = {
                "summary": EventsEnum[event_type_name],
                "value": example,
            }
            continue
        # elif example_number == 2:
        #     examples[event_type]["summary"] += " 1"
        #     examples[f"{event_type} 1"] = examples.pop(event_type)

        input_examples[f"{event_type_name} {example_number}"] = {
            "summary": f"{EventsEnum[event_type_name]} {example_number}",
            "value": example,
        }

    return input_examples
