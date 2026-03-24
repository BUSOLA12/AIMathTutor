from app.session.manager import get_session_state, save_session_state


async def register_interruption(session_id: str, question_text: str) -> bool:
    """Marks an interruption as pending in session state. Returns True if session found."""
    state = await get_session_state(session_id)
    if state is None:
        return False
    state.phase = "interrupted"
    state.interruption_text = question_text
    state.interruptions_count += 1
    await save_session_state(state)
    return True
