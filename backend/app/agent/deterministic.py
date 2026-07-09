"""Deterministic reasoning engine (offline planner).

Drives the exact same tool-calling loop as the LLM path, but decides the next
step with rules instead of a model. It reads the provider-agnostic message list
— the current user message, the prior turn for context, and any tool results
gathered this turn — and returns the next `Step` (a tool call, or a final
answer).

Designed to be robust and conversational: it answers human/chit-chat inputs
gracefully, never calls a write tool without a target order, picks the right
order id for an action in multi-order messages, carries a pending action across
one turn, and only searches the knowledge base for genuine store/policy
questions (so it never grounds an answer in an irrelevant doc). It is not a
replacement for the LLM's reasoning; it exists so the product runs end-to-end
with no API key, and so the deterministic path can be A/B'd against Claude.
"""
from __future__ import annotations

import re

from app.agent.llm import Step, ToolCall

ORD_RE = re.compile(r"ORD-?0*(\d{1,5})", re.IGNORECASE)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

INJECTION_MARKERS = (
    "ignore your instructions", "ignore previous", "ignore all previous", "system prompt",
    "you are now", "developer mode", "disregard your", "100% discount", "free money",
    "reveal your prompt", "print your instructions", "jailbreak",
)
# Explicit request to be handed to a human (needs request phrasing, so
# "are you a real person?" is NOT treated as a handoff request).
HUMAN_REQUEST_MARKERS = (
    "speak to a human", "talk to a human", "speak to a manager", "talk to a manager",
    "speak to someone", "talk to someone", "speak to a person", "talk to a person",
    "real person", "human agent", "human being", "representative", "supervisor",
    "get me a human", "connect me", "transfer me", "escalate", "manager", "a manager",
)
PRODUCT_MARKERS = (
    "do you sell", "do you have", "do you carry", "do you stock", "in stock", "out of stock",
    "availability", "available", "what products", "product catalog", "your catalog", "what do you sell",
)
LEGAL_MARKERS = (
    "lawyer", "sue you", "i'll sue", "legal action", "attorney", "chargeback", "charge back",
    "reporting you", "report you", "bbb", "better business bureau", "fraud", "press charges",
)
DISTRESS_MARKERS = (
    "unacceptable", "ridiculous", "furious", "outrageous", "worst", "terrible", "disgusting",
    "never again", "third time", "3rd time", "fed up", "sick of",
)
INSULT_MARKERS = ("useless", "stupid", "dumb", "idiot", "you suck", "garbage", "hate you", "pathetic", "worthless")
EMOTION_NEG = ("frustrat", "annoy", "upset", "angry", "so mad", "i'm mad", "disappointed", "unhappy",
               "not happy", "let down", "fed up", "irritat")
# Mood / feeling detection, so the agent responds to how the customer feels.
POSITIVE_EMOTION = ("i'm happy", "im happy", "so happy", "really happy", "i'm great", "im great",
                    "i'm good", "im good", "doing great", "doing well", "feeling great", "feeling good",
                    "excited", "thrilled", "wonderful", "great news", "good news", "best day", "happy today",
                    "in a good mood", "over the moon", "made my day", "so glad", "i'm well", "great day",
                    "good day", "lovely day", "amazing day", "having a great", "having a good", "got the job",
                    "feeling wonderful", "feeling happy", "life is good")
SAD_EMOTION = ("i'm sad", "im sad", "so sad", "feeling down", "feeling low", "depressed", "heartbroken",
               "bad day", "terrible day", "awful day", "rough day", "hard day", "worst day", "not doing well",
               "feeling awful", "feeling terrible", "i'm down", "so stressed", "stressed out", "overwhelmed",
               "exhausted", "burnt out", "burned out", "crying", "feel like crying", "lonely", "hopeless",
               "having a hard time", "going through a lot", "really down", "so down", "down today",
               "feeling really down", "low today", "miserable", "feeling sad", "not okay", "not ok")
ANXIOUS_MARKERS = ("worried", "nervous", "anxious", "scared", "afraid", "concerned", "stressing",
                   "freaking out", "panicking", "on edge", "uneasy")
CONFUSED_MARKERS = ("confused", "don't understand", "dont understand", "not sure what", "what do you mean",
                    "i'm lost", "im lost", "makes no sense", "don't get it", "dont get it", "unclear",
                    "so confusing", "bit lost", "feeling lost", "little lost", "so lost", "kinda lost",
                    "i am lost", "totally lost")
IMPATIENT_MARKERS = ("hurry", "taking forever", "taking too long", "taking so long", "still waiting",
                     "how much longer", "been waiting", "waiting forever", "right now", "immediately",
                     "come on", "hurry up")
APOLOGETIC_MARKERS = ("sorry to bother", "sorry to ask", "sorry for asking", "hate to bother",
                      "apologies for", "sorry if", "sorry for the trouble", "don't mean to bother")
WELLBEING_MARKERS = ("how are you", "how're you", "how are u", "how are things", "how you doing",
                     "how are you doing", "how have you been", "you doing ok", "you doing okay",
                     "how's your day", "hows your day", "how is your day", "how's it going", "hows it going")
COMPLIMENT_MARKERS = ("amazing", "awesome", "you're great", "youre great", "you are great",
                      "love you", "you rock", "brilliant", "fantastic", "so helpful", "the best")
THANKS_MARKERS = ("thank", "thanks", "thx", "appreciate", "cheers")
GOODBYE_MARKERS = ("bye", "goodbye", "see you", "see ya", "that's all", "thats all", "that is all",
                   "we're done", "were done", "have a good", "take care")
CHITCHAT_MARKERS = ("joke", "how are you", "how's your day", "hows your day", "what's up", "whats up",
                    "how's it going", "hows it going", "do you like", "favorite", "favourite", "sing",
                    "poem", "bored", "your day", "weather", "meaning of life")
IDENTITY_MARKERS = ("who are you", "are you a bot", "are you a robot", "are you human",
                    "are you real", "are you a real", "are you an ai", "are you ai", "your name",
                    "who am i talking", "am i talking to a", "are you a person", "are you a machine")
# "what are you" as a standalone identity question, but NOT "what are your <X>".
IDENTITY_RE = re.compile(r"\bwhat are you\b")
CAPABILITY_MARKERS = ("what can you do", "what do you do", "how can you help", "what are you able",
                      "what can i ask", "what do you offer", "how do you work", "what can you help")
AFFIRM_WORDS = {"ok", "okay", "yes", "yep", "yeah", "yup", "no", "nope", "sure", "fine", "alright", "k", "cool", "great"}

REFUND_MARKERS = ("refund", "money back", "my money", "reimburse", "give me back", "return my money")
CANCEL_MARKERS = ("cancel",)
ADDRESS_MARKERS = ("address", "change delivery", "change the delivery", "ship it to", "deliver it to",
                   "reroute", "new address", "wrong address", "update shipping", "change shipping")
RETURN_MARKERS = ("return", "send it back", "send back")
STATUS_MARKERS = ("where", "track", "status", "when will", "arrive", "delivered yet", "shipped", "eta",
                  "delivery", "where's", "wheres")
POLICY_MARKERS = (
    "policy", "return window", "how long", "how many days", "warranty", "damaged", "broken",
    "hours", "open", "international", "shipping cost", "how much is shipping", "do you ship",
    "can i return", "non-returnable", "exchange", "gift card",
)
# A message is a store/policy question only if it mentions one of these topics.
STORE_TOPIC = (
    "order", "refund", "return", "ship", "deliver", "track", "cancel", "warrant", "damage",
    "broken", "defect", "policy", "hour", "payment", " pay", "card", "address", "item", "product",
    "stock", "price", "gift card", "exchange", "international", "eta", "arrive", "package", "parcel",
    "money back", "receipt", "invoice", "carrier", "label", "restock", "pay",
)
POLICY_FRAMING = (
    "how do", "how does", "how long", "how many", "what's your", "whats your", "what is your",
    "what are your", "policy", "process", "within", "after", "do i have to", "am i able",
    "what happens", "how much", "are there", "is there", "can i return", "do you offer",
)
QUESTION_WORDS = ("what", "when", "where", "why", "how", "who", "which", "can ", "do ", "does ",
                  "is ", "are ", "could ", "would ", "should ", "will ")


def _fmt(num: str) -> str:
    return f"ORD-{int(num):05d}"


def _norm_order_id(text: str) -> str | None:
    m = ORD_RE.search(text)
    return _fmt(m.group(1)) if m else None


def _order_id_for(text: str, markers: tuple[str, ...]) -> str | None:
    """Pick the order id tied to an action keyword (the first id at/after it),
    so 'where is ORD-00012 and refund ORD-00007' refunds ORD-00007, not -00012."""
    matches = list(ORD_RE.finditer(text))
    if not matches:
        return None
    t = text.lower()
    positions = [t.find(m) for m in markers if m in t]
    if positions:
        pos = min(positions)
        for m in matches:
            if m.start() >= pos:
                return _fmt(m.group(1))
    return _fmt(matches[0].group(1))


def _has(text: str, markers) -> bool:
    return any(m in text for m in markers)


def _has_word(text: str, markers) -> bool:
    """Word-START boundary (prefix) match: 'refund' matches 'refund/refunds/
    refunded' but NOT 'broken' inside 'heartbroken' or 'ship' inside
    'relationship'. Handles plurals/tenses while rejecting mid-word matches."""
    return any(re.search(r"\b" + re.escape(m), text) for m in markers)


def _is_question(t: str) -> bool:
    return "?" in t or t.startswith(QUESTION_WORDS)


def _alnum(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------
def _detect_intent(text: str) -> str:
    t = text.lower().strip()
    if not _alnum(t):
        return "smalltalk"  # empty / punctuation / emoji-only

    if _has(t, INJECTION_MARKERS):
        return "injection"

    # Identity / capability first, so "are you a real person?" isn't a handoff.
    if _has(t, IDENTITY_MARKERS) or IDENTITY_RE.search(t):
        return "identity"
    if _has(t, CAPABILITY_MARKERS):
        return "capability"

    # Explicit human handoff, legal/chargeback, or distress + a demand -> escalate.
    if _has(t, HUMAN_REQUEST_MARKERS) or _has(t, LEGAL_MARKERS):
        return "escalation"
    if _has(t, DISTRESS_MARKERS) and (_has(t, REFUND_MARKERS) or t.count("order") > 1):
        return "escalation"

    # With a concrete order id: an action/status request on that order.
    if _norm_order_id(t):
        if _has(t, REFUND_MARKERS) or _has(t, RETURN_MARKERS):
            return "refund"
        if _has(t, ADDRESS_MARKERS) or _extract_address(t):
            return "address_change"
        if _has(t, CANCEL_MARKERS):
            return "cancel"
        return "order_status"

    # No order id. Product/catalog questions get a tailored answer.
    if _has(t, PRODUCT_MARKERS):
        return "product"

    # An informationally-framed store question -> knowledge base (this wins over
    # an action word, so "how long do refunds take" is a question, not an action).
    # Word-boundary matching so mood words like "heartbroken" aren't read as store topics.
    store = _has_word(t, STORE_TOPIC) or _has_word(t, POLICY_MARKERS)
    policyish = _has(t, POLICY_FRAMING) or _has_word(t, POLICY_MARKERS)
    if store and policyish:
        return "policy_qa"

    # Action requests without an id (ask for the order number).
    if _has(t, REFUND_MARKERS) or _has(t, RETURN_MARKERS):
        return "refund"
    if _has(t, CANCEL_MARKERS):
        return "cancel"
    if _has(t, ADDRESS_MARKERS):
        return "address_change"
    if _has(t, STATUS_MARKERS):
        return "order_status"
    # Vague store mention: a question -> KB; otherwise ask which order.
    if store and _is_question(t):
        return "policy_qa"
    if store:
        return "order_status"

    # Human / conversational — read the mood and respond to how they feel.
    if _has(t, WELLBEING_MARKERS):
        return "wellbeing"
    if _has(t, APOLOGETIC_MARKERS):
        return "apologetic"
    if _has(t, POSITIVE_EMOTION):
        return "positive_emotion"
    if _has(t, CONFUSED_MARKERS):
        return "confused"
    if _has(t, SAD_EMOTION):
        return "sad"
    if _has(t, ANXIOUS_MARKERS):
        return "anxious"
    if _has(t, IMPATIENT_MARKERS):
        return "impatient"
    if _has(t, THANKS_MARKERS):
        return "thanks"
    if _has(t, GOODBYE_MARKERS):
        return "goodbye"
    if _has(t, COMPLIMENT_MARKERS):
        return "compliment"
    if _has(t, INSULT_MARKERS) or _has(t, DISTRESS_MARKERS) or _has(t, EMOTION_NEG):
        return "frustration"
    if _has(t, CHITCHAT_MARKERS):
        return "chitchat"
    if t.split() and all(w.strip(".,!?") in AFFIRM_WORDS for w in t.split()) and len(t.split()) <= 3:
        return "affirm"
    if _is_question(t):
        return "offtopic_question"
    return "smalltalk"


def _prior_assistant_text(messages: list[dict]) -> str:
    """The agent's previous reply (for one-turn intent carryover)."""
    last_user = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=0)
    for m in reversed(messages[:last_user]):
        if m["role"] == "assistant" and m.get("content"):
            c = m["content"]
            return c if isinstance(c, str) else " ".join(str(x) for x in c)
    return ""


def _parse(messages: list[dict]) -> tuple[str, dict]:
    """Return (current user text, {tool_name: [results this turn]})."""
    last_user_idx = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=0)
    user_text = messages[last_user_idx]["content"]
    if isinstance(user_text, list):
        user_text = " ".join(str(x) for x in user_text)
    results: dict[str, list] = {}
    for m in messages[last_user_idx + 1:]:
        if m["role"] == "tool":
            results.setdefault(m["name"], []).append(m["content"])
    return user_text, results


def _tc(name: str, **kwargs) -> Step:
    return Step(kind="tool_use", tool_calls=[ToolCall(name=name, input=kwargs)])


def _final(text: str) -> Step:
    return Step(kind="final", text=text)


CAPABILITIES = ("check where an order is, process a refund within policy, change a shipping address "
                "before it ships, cancel an order, and answer questions about our policies")


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------
def plan_next_step(messages: list[dict], tools: list[dict]) -> Step:
    user_text, results = _parse(messages)
    intent = _detect_intent(user_text)
    order_id = _norm_order_id(user_text)

    # One-turn intent carryover: a bare order id after we asked for one.
    if intent == "order_status" and order_id and not results:
        prior = _prior_assistant_text(messages).lower()
        bare = not _has(user_text.lower(), STATUS_MARKERS)
        if bare and "order number" in prior:
            if "refund" in prior:
                intent = "refund"
            elif "cancel" in prior:
                intent = "cancel"
            elif "address" in prior:
                intent = "address_change"

    if intent == "injection":
        return _final(
            "I'm not able to do that. I can only help with your Northwind Goods orders — "
            f"I can {CAPABILITIES}. How can I help with your order today?")

    if intent == "escalation":
        return _plan_escalation(user_text, results)
    if intent == "order_status":
        return _plan_order_status(_order_id_for(user_text, STATUS_MARKERS) or order_id, results)
    if intent == "refund":
        return _plan_refund(_order_id_for(user_text, REFUND_MARKERS + RETURN_MARKERS), user_text, results)
    if intent == "address_change":
        return _plan_address(_order_id_for(user_text, ADDRESS_MARKERS), user_text, results)
    if intent == "cancel":
        return _plan_cancel(_order_id_for(user_text, CANCEL_MARKERS), results)
    if intent == "policy_qa":
        return _plan_policy(user_text, results)

    # --- conversational intents ---
    if intent == "identity":
        return _final(
            "I'm the Northwind Goods support assistant — a virtual (AI) agent, not a human. "
            f"I can {CAPABILITIES}. What can I help you with today?")
    if intent == "capability":
        return _final(
            f"Happy to help! I can {CAPABILITIES}. If you have an order number (like ORD-00012), "
            "share it and I'll take a look — or just tell me what's going on.")
    if intent == "wellbeing":
        return _final(
            "I'm doing great, thanks for asking! 🙂 I'm here and ready to help. Is there something I can "
            "do for you today — check an order, sort out a refund, or answer a question?")
    if intent == "positive_emotion":
        return _final(
            "That's wonderful to hear — thanks for sharing, it made my day too! Is there anything I can help "
            "you with while you're here, like an order or a policy question?")
    if intent == "sad":
        return _final(
            "I'm really sorry you're having a tough time — I hope things start looking up for you soon. "
            "If there's anything about an order I can take off your plate, I'm right here to help; just share "
            "your order number or tell me what's going on, and I'll do my best to make it easy.")
    if intent == "anxious":
        return _final(
            "I completely understand, and I'd feel the same — let's put your mind at ease. If it's about an "
            "order, share the order number and I'll check its exact status and ETA right away so you know "
            "precisely where things stand.")
    if intent == "confused":
        return _final(
            "No worries at all — let's clear it up together. Could you tell me a little more about what you're "
            "trying to do, or share your order number? I can check status, process a refund, update shipping, "
            "cancel an order, or explain any of our policies.")
    if intent == "impatient":
        return _final(
            "I hear you, and I don't want to keep you waiting — let's get this handled fast. What's your order "
            "number? I'll pull up the status and ETA right now.")
    if intent == "apologetic":
        return _final(
            "Please don't apologize — that's exactly what I'm here for, and it's no bother at all! What can I "
            "help you with?")
    if intent == "thanks":
        return _final("You're very welcome! Is there anything else I can help you with?")
    if intent == "goodbye":
        return _final("Thanks for chatting — take care! Reach out anytime you need help with an order.")
    if intent == "compliment":
        return _final("That's very kind — thank you! What can I help you with today?")
    if intent == "frustration":
        return _final(
            "I'm sorry for the frustration — let's get it sorted. Tell me your order number or what you're "
            "trying to do (track an order, a refund, an address change, or a cancellation) and I'll jump on it. "
            "If you'd rather speak with a human specialist, just say so.")
    if intent == "product":
        return _final(
            "I can't browse our live product catalog or stock levels from here — but I can help with any order "
            "you've already placed (status, refund, address change, cancellation) or answer questions about our "
            "policies. Do you have an order number, or a policy question I can help with?")
    if intent == "chitchat":
        return _final(
            "Ha — I'm just the Northwind support assistant, so I'll stick to what I'm good at: your orders and "
            f"our policies. I can {CAPABILITIES}. Anything there I can help with?")
    if intent == "affirm":
        return _final(
            "Got it! What would you like to do — check an order, start a refund, update a shipping address, "
            "cancel an order, or ask about a policy?")
    if intent == "offtopic_question":
        return _final(
            "I'm Northwind's support assistant, so that's a bit outside what I can help with — but I'm great "
            f"with anything about your orders or our policies. I can {CAPABILITIES}. What can I do for you?")

    # smalltalk / greeting / fallback
    return _final(
        "Hi! I'm the Northwind Goods support assistant. I can check where your order is, process a refund "
        "within policy, change a shipping address before it ships, or cancel an order — and answer questions "
        "about our policies. What can I help you with? If you have an order number (like ORD-00012), share it "
        "and I'll take a look.")


def _plan_escalation(user_text: str, results: dict) -> Step:
    if "escalate_to_human" not in results:
        summary = (f"Customer message: \"{user_text.strip()[:280]}\". "
                   "Customer requested a human and/or raised a legal/chargeback concern that requires human judgment.")
        return _tc("escalate_to_human", reason="Human handoff requested / legal or chargeback concern", summary=summary)
    return _final(
        "Of course — I've connected you with a senior specialist and passed along a full summary of your case, "
        "so you won't have to repeat yourself. They'll follow up directly. Is there anything I can note for them "
        "in the meantime?")


def _plan_order_status(order_id: str | None, results: dict) -> Step:
    if not order_id:
        return _final("Happy to check on that — what's your order number? It looks like ORD-00012.")
    if "lookup_order" not in results:
        return _tc("lookup_order", order_id=order_id)
    order = results["lookup_order"][-1]
    if isinstance(order, dict) and order.get("error"):
        return _final(
            f"I couldn't find an order with the id {order_id}. Could you double-check the number? "
            "It should look like ORD-00012.")
    status = order.get("status")
    if status == "processing":
        return _final(
            f"Your order {order_id} is still being processed and hasn't shipped yet. You'll get a tracking "
            "number by email as soon as it's on its way. Anything else I can help with?")
    if status in ("cancelled", "refunded"):
        return _final(f"Order {order_id} is currently marked as **{status}**. Let me know if you'd like details.")
    if status == "shipped" and "track_shipment" not in results:
        return _tc("track_shipment", order_id=order_id)
    shipment = results.get("track_shipment", [{}])[-1] if "track_shipment" in results else {}
    return _final(_compose_status(order_id, order, shipment))


def _compose_status(order_id: str, order: dict, shipment: dict) -> str:
    items = ", ".join(f"{i['qty']}× {i['product_name']}" for i in order.get("items", []))
    if order.get("status") == "delivered":
        return (f"Good news — order {order_id} ({items}) has been **delivered**. "
                "If anything arrived damaged or you'd like to start a return, just say the word.")
    if shipment and not shipment.get("error"):
        eta = shipment.get("eta", "")
        eta_str = f" Estimated delivery is around {eta[:10]}." if eta else ""
        carrier = shipment.get("carrier", "the carrier")
        tn = shipment.get("tracking_number", "")
        st = shipment.get("status", "in transit").replace("_", " ")
        delayed = " I can see it's currently marked as **delayed** — apologies for the wait." if shipment.get("status") == "delayed" else ""
        return (f"Your order {order_id} ({items}) is **{st}** with {carrier} (tracking {tn}).{eta_str}{delayed} "
                "Anything else I can help with?")
    return f"Your order {order_id} ({items}) is currently **{order.get('status')}**."


def _plan_refund(order_id: str | None, user_text: str, results: dict) -> Step:
    if not order_id:
        return _final(
            "I can help with a refund. What's the order number you'd like refunded? It looks like ORD-00012.")
    if "check_refund_eligibility" not in results:
        return _tc("check_refund_eligibility", order_id=order_id)
    elig = results["check_refund_eligibility"][-1]
    if isinstance(elig, dict) and elig.get("error"):
        return _final(f"I couldn't find order {order_id} to check it. Could you confirm the order number?")
    if not elig.get("eligible"):
        reason = elig.get("reason", "It falls outside our refund policy.")
        return _final(
            f"I looked into a refund for {order_id}, but I'm not able to process it: {reason} I know that's not "
            "what you hoped to hear. If the item arrived damaged or defective I can open a separate claim, or I "
            "can connect you with a specialist to review your options — just let me know.")
    if "process_refund" not in results:
        amount = elig.get("order_total_cents", 0)
        return _tc("process_refund", order_id=order_id, amount_cents=amount, reason="Customer requested refund")
    res = results["process_refund"][-1]
    status = res.get("status")
    if status == "pending_approval":
        return _final(
            f"Because this refund ({res.get('amount')}) is above our automatic-approval limit, I've submitted it "
            "for a quick human review to protect your account. You'll get a confirmation by email shortly — you "
            "don't need to do anything else. Is there anything else I can help with in the meantime?")
    if status == "processed":
        return _final(
            f"Done — I've processed your refund of **{res.get('amount')}** for order {order_id}. It'll appear on "
            "your original payment method within 5–7 business days. Sorry for the trouble, and thank you for your "
            "patience!")
    return _final(f"I wasn't able to complete that refund: {res.get('reason', 'please contact support.')}")


def _plan_address(order_id: str | None, user_text: str, results: dict) -> Step:
    if not order_id:
        return _final(
            "I can update the delivery address as long as the order hasn't shipped. What's the order number, "
            "and the full new address?")
    if "update_shipping_address" not in results:
        new_address = _extract_address(user_text)
        if not new_address:
            return _final(
                f"I can update the delivery address on {order_id} as long as it hasn't shipped. "
                "What's the full new address?")
        return _tc("update_shipping_address", order_id=order_id, new_address=new_address)
    res = results["update_shipping_address"][-1]
    if res.get("status") == "updated":
        return _final(
            f"All set — I've updated the shipping address on {order_id} to **{res.get('shipping_address')}**. "
            "It'll ship to the new address. Anything else?")
    return _final(
        f"I wasn't able to change the address on {order_id}: {res.get('reason', 'it may have already shipped.')} "
        "If it's already on its way, I can help you reroute it with the carrier or start a return once it arrives.")


def _plan_cancel(order_id: str | None, results: dict) -> Step:
    if not order_id:
        return _final("Sure — what's the order number you'd like to cancel? It looks like ORD-00012.")
    if "cancel_order" not in results:
        return _tc("cancel_order", order_id=order_id)
    res = results["cancel_order"][-1]
    if res.get("status") == "cancelled":
        return _final(
            f"Done — order {order_id} has been **cancelled** and you won't be charged. If you paid already, the "
            "hold will drop off in a few business days. Anything else I can do?")
    return _final(
        f"I couldn't cancel {order_id}: {res.get('reason', 'it may have already shipped.')} If it's shipped, I can "
        "help you start a return as soon as it arrives.")


def _plan_policy(user_text: str, results: dict) -> Step:
    if "search_knowledge_base" not in results:
        return _tc("search_knowledge_base", query=user_text)
    kb = results["search_knowledge_base"][-1]
    passages = kb.get("passages", []) if isinstance(kb, dict) else []
    if not passages:
        return _final(
            "I don't have that in our policy documents, so I don't want to guess. I can connect you with a "
            "specialist who can confirm, or help with an order if you have its number — what works best?")
    top = passages[0]
    cite = f"{top['source']}" + (f" › {top['section']}" if top.get("section") else "")
    return _final(
        f"{top['snippet'].strip()}\n\n*Source: {cite}.* Let me know if you'd like more detail or have a specific "
        "order in mind.")


def _extract_address(text: str) -> str | None:
    """Best-effort address extraction for 'change my address to ...'."""
    for kw in (" to ", " to:", "address:", "address is ", " at "):
        idx = text.lower().find(kw)
        if idx != -1:
            candidate = text[idx + len(kw):].strip(" .")
            for tail in (" instead", " please", ", please"):
                if candidate.lower().endswith(tail):
                    candidate = candidate[: -len(tail)].strip(" .,")
            if len(candidate) >= 6 and any(ch.isdigit() for ch in candidate):
                return candidate
    return None
