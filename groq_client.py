import config

SYSTEM_PROMPT = (
    "You are a market data analyst describing a technical indicator reading that just fired on a chart. "
    "Write 2-4 plain-English sentences explaining what the signal means mechanically and what a trader "
    "would typically watch for next. Do not predict future price direction with certainty, do not give "
    "buy, sell, or hold recommendations, and avoid words like 'guaranteed' or 'sure thing'. "
    "This is descriptive commentary on the indicator data only, not financial advice."
)


def explain_signal(client, ticker, signal_type, detail, snapshot):
    user_prompt = (
        f"Ticker: {ticker}\n"
        f"Signal: {signal_type}\n"
        f"Detail: {detail}\n"
        f"Recent snapshot: close={snapshot['Close']:.2f}, "
        f"MACD={snapshot['MACD']:.3f}, MACD signal={snapshot['MACD_SIGNAL']:.3f}, "
        f"VWAP={snapshot['VWAP']:.2f}\n\n"
        "Explain this signal."
    )
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=220,
    )
    return resp.choices[0].message.content.strip()


def synthesize_outlook(client, ticker, outlook, news_items, composite, confirm_composite):
    """Hedged near-term outlook grounded in: detected candlestick patterns,
    a simple trend/momentum read, the composite technical score, and real
    fetched news headlines. Explicitly told not to predict with confidence."""
    patterns_txt = "\n".join(
        f"- {p['pattern']} ({p['direction']}) at {p['time']}" for p in outlook["recent_patterns"]
    ) or "- No notable candlestick patterns in the recent window."

    if news_items:
        news_txt = "\n".join(f"- {n['title']} ({n.get('publisher','unknown source')})" for n in news_items)
    else:
        news_txt = "No recent news headlines were available."

    user_prompt = (
        f"Ticker: {ticker}\n\n"
        f"Recent trend: {outlook['trend_direction']} "
        f"(slope {outlook['slope_pct_per_bar']}%/bar, {outlook['roc_pct']}% over the lookback window)\n"
        f"Candlestick pattern bias: {outlook['pattern_bias']}\n"
        f"Recent patterns detected:\n{patterns_txt}\n\n"
        f"Composite technical reading: {composite['label']} (score {composite['score']})\n"
        f"Higher-timeframe reading: {confirm_composite['label'] if confirm_composite else 'unavailable'}\n\n"
        f"Recent news headlines:\n{news_txt}\n\n"
        "Write a 3-5 sentence near-term outlook that weaves together the pattern bias, the trend read, "
        "and the tone of the news headlines (if any relate to the ticker). Explicitly hedge — use language "
        "like 'leans toward' or 'suggests', never 'will' or 'is going to'. Do not give a buy/sell instruction "
        "or a confident price prediction. If the signals conflict, say so plainly. If the news headlines are "
        "unrelated to price direction, or unavailable, be honest about that rather than forcing a connection."
    )
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=280,
    )
    return resp.choices[0].message.content.strip()


def synthesize_reasoning(client, ticker, composite, confirm_composite, mtf_confirmed):
    """Turn the deterministic indicator breakdown into a grounded narrative.
    The model is only asked to explain numbers it's given — not to invent
    new signals — which keeps this from drifting into speculation."""
    lines = "\n".join(
        f"- {b['name']}: {b['reading']} -> {b['vote']} ({b['explanation']})"
        for b in composite["breakdown"]
    )
    confirm_note = "confirms" if mtf_confirmed else "does not confirm"
    user_prompt = (
        f"Ticker: {ticker}\n"
        f"Composite reading: {composite['label']} "
        f"(score {composite['score']}, confidence {composite['confidence']}%, "
        f"trend strength {composite['trend_strength']})\n"
        f"Higher-timeframe reading: {confirm_composite['label']} (score {confirm_composite['score']})\n"
        f"The higher timeframe {confirm_note} the primary-timeframe reading.\n"
        f"Indicator breakdown:\n{lines}\n\n"
        "In 3-5 sentences, explain in plain English why the indicators point this way right now. "
        "Reference the strongest agreeing signals and call out anything that disagrees. "
        "Do not give a buy/sell instruction or predict future price — describe what the data shows."
    )
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=280,
    )
    return resp.choices[0].message.content.strip()


def synthesize_trade_plan(client, ticker, plan, composite):
    if plan["direction"] == "none":
        return plan.get("reason", "No reference plan is available right now.")
    hist = plan.get("historical_time_to_target")
    hist_line = (
        f"Historically, moves of this size took a median of {hist['median_bars']} bars "
        f"across {hist['sample_size']} observed instances in this ticker's own recent data."
        if hist else "No reliable historical timing sample was available for a move this size."
    )
    user_prompt = (
        f"Ticker: {ticker}\n"
        f"Composite reading: {composite['label']} (score {composite['score']})\n"
        f"Reference plan direction: {plan['direction']}\n"
        f"Limit entry: {plan['entry']}, Stop: {plan['stop']}, Target: {plan['target']}\n"
        f"Risk per share: {plan['risk_per_share']}, Reward per share: {plan['reward_per_share']}, "
        f"Reward:Risk {plan['reward_risk_ratio']}:1\n"
        f"Order mechanics: {plan['entry_mechanics']}\n"
        f"{hist_line}\n\n"
        "In 3-4 sentences, explain what this reference plan means and how it would mechanically play out. "
        "Make clear this is a rule-based reference level (ATR and support/resistance based), not a "
        "personalized recommendation, and that fills, stops, and targets are never guaranteed. "
        "Do not promise a specific outcome or timeframe with certainty."
    )
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=260,
    )
    return resp.choices[0].message.content.strip()


def synthesize_dummy_explanation(client, ticker, composite, outlook, plan, confirm_composite):
    """A full plain-English rewrite of everything on the reasoning panel,
    for someone who has never traded before."""
    lines = "\n".join(f"- {b['name']}: {b['reading']} -> {b['vote']}" for b in composite["breakdown"])
    if plan["direction"] == "none":
        plan_txt = "No reference trade plan was generated because the signals are mixed right now."
    else:
        plan_txt = (
            f"Reference plan: {plan['direction']} — limit entry {plan['entry']}, "
            f"stop {plan['stop']}, target {plan['target']}."
        )
    user_prompt = (
        f"Ticker: {ticker}\n"
        f"Composite label: {composite['label']}\n"
        f"Higher-timeframe reading: {confirm_composite['label'] if confirm_composite else 'unavailable'}\n"
        f"Indicator readings:\n{lines}\n"
        f"Trend/pattern outlook: {outlook['trend_direction']} trend, pattern bias {outlook['pattern_bias']}\n"
        f"{plan_txt}\n\n"
        "Explain ALL of this to a complete beginner who has never traded before. Avoid jargon — if you use "
        "a technical term, immediately explain it in one plain phrase right after. Cover: what the overall "
        "reading means and why, what the outlook suggests, and what the reference trade plan (if any) means "
        "mechanically. Be encouraging but honest that nothing here is guaranteed and this is not financial "
        "advice. Use short paragraphs. Aim for roughly 150-220 words."
    )
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,
        max_tokens=420,
    )
    return resp.choices[0].message.content.strip()
