"""UI-TARS-1.5 client: prompts, llama-server calls and action parsing.

Prompts follow the UI-TARS repo (codes/ui_tars/prompt.py). UI-TARS-1.5 returns
absolute pixel coordinates on the image it received; we send images whose sides
are multiples of 28, so those coordinates map 1:1 onto the image we sent.
"""

import ast
import base64
import io
import re
from dataclasses import dataclass, field

import requests
from PIL import Image

COMPUTER_USE = r"""You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Output Format
```
Thought: ...
Action: ...
```

## Action Space

click(start_box='<|box_start|>(x1,y1)<|box_end|>')
left_double(start_box='<|box_start|>(x1,y1)<|box_end|>')
right_single(start_box='<|box_start|>(x1,y1)<|box_end|>')
drag(start_box='<|box_start|>(x1,y1)<|box_end|>', end_box='<|box_start|>(x3,y3)<|box_end|>')
hotkey(key='')
type(content='') #If you want to submit your input, use "\n" at the end of `content`.
scroll(start_box='<|box_start|>(x1,y1)<|box_end|>', direction='down or up or right or left')
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.


## Note
- Use {language} in `Thought` part and in `finished(content=...)`.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{instruction}
"""

GROUNDING = "Output only the coordinate of one point in your response. What element matches the following task: {instruction}"


@dataclass
class Action:
    kind: str                                   # click, left_double, right_single, drag, hotkey, type, scroll, wait, finished
    points: list[tuple[float, float]] = field(default_factory=list)  # model-image coordinates
    text: str = ""                              # hotkey combo, typed content or finished message
    direction: str = ""                         # scroll direction


@dataclass
class Step:
    thought: str
    action: Action
    raw: str


def image_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _points(arg: str) -> list[tuple[float, float]]:
    """Extract one point from '(x,y)', '(x1,y1,x2,y2)' or '<point>x y</point>'."""
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", arg)]
    if len(nums) >= 4:  # box: use its center
        return [((nums[0] + nums[2]) / 2, (nums[1] + nums[3]) / 2)]
    if len(nums) >= 2:
        return [(nums[0], nums[1])]
    raise ValueError(f"No coordinates in {arg!r}")


def _string(arg: str) -> str:
    try:
        return ast.literal_eval(arg)
    except (ValueError, SyntaxError):
        return arg.strip("'\"")


def parse_action(text: str) -> Action:
    m = re.match(r"\s*(\w+)\s*\((.*)\)\s*$", text, re.S)
    if not m:
        raise ValueError(f"Cannot parse action: {text!r}")
    kind, args_src = m[1], m[2]
    # key='value' pairs; values may contain escaped quotes
    args = {k: v for k, v in re.findall(r"(\w+)\s*=\s*('(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")", args_src, re.S)}
    act = Action(kind)
    for key in ("start_box", "point", "start_point"):
        if key in args:
            act.points += _points(args[key])
    for key in ("end_box", "end_point"):
        if key in args:
            act.points += _points(args[key])
    if "key" in args:
        act.text = _string(args["key"])
    if "content" in args:
        act.text = _string(args["content"])
    if "direction" in args:
        act.direction = _string(args["direction"]).lower()
    return act


def parse_response(raw: str) -> Step:
    thought = re.search(r"Thought:\s*(.*?)(?=\nAction:|$)", raw, re.S)
    action = re.search(r"Action:\s*(.*)", raw, re.S)
    if not action:
        raise ValueError(f"No 'Action:' in model output:\n{raw}")
    # Only the first action line counts.
    first = action[1].strip().split("\n\n")[0].strip()
    return Step(thought[1].strip() if thought else "", parse_action(first), raw)


class UITars:
    def __init__(self, base_url: str, coords: str = "absolute", history: int = 3, language: str = "English"):
        self.url = base_url.rstrip("/") + "/v1/chat/completions"
        self.coords = coords        # "absolute" (UI-TARS-1.5) or "relative" (0-1000, UI-TARS-1.0 / Qwen3-VL)
        self.history = history      # how many past screenshots to keep in context
        self.language = language

    def _chat(self, messages: list[dict], max_tokens: int = 512) -> str:
        r = requests.post(self.url, json={
            "messages": messages, "temperature": 0.0, "max_tokens": max_tokens,
        }, timeout=300)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def to_image_px(self, point: tuple[float, float], img: Image.Image) -> tuple[float, float]:
        if self.coords == "relative":
            return point[0] * img.width / 1000, point[1] * img.height / 1000
        return point

    def next_step(self, instruction: str, past: list[tuple[Image.Image, str]], screenshot: Image.Image,
                  note: str = "") -> Step:
        """past: earlier (screenshot, raw response) pairs, oldest first.

        note: extra feedback shown with the current screenshot, e.g. that the
        previous action changed nothing on screen.
        """
        messages = [{"role": "user", "content": COMPUTER_USE.format(language=self.language, instruction=instruction)}]
        # Keep text of every earlier step but only the last few screenshots.
        keep_images_from = max(0, len(past) - (self.history - 1))
        for i, (img, raw) in enumerate(past):
            if i >= keep_images_from:
                messages.append({"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_url(img)}}]})
            messages.append({"role": "assistant", "content": raw})
        content = [{"type": "image_url", "image_url": {"url": image_url(screenshot)}}]
        if note:
            content.append({"type": "text", "text": note})
        messages.append({"role": "user", "content": content})
        return parse_response(self._chat(messages))

    def ground(self, description: str, screenshot: Image.Image) -> tuple[float, float]:
        """Return image-pixel coordinates of the element matching description."""
        raw = self._chat([{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": image_url(screenshot)}},
            {"type": "text", "text": GROUNDING.format(instruction=description)},
        ]}], max_tokens=64)
        return self.to_image_px(_points(raw)[0], screenshot)
