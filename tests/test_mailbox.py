from swarmflight.runtime import Mailbox, Message


def test_mailbox_send_receive_round_trip():
    mailbox = Mailbox()
    message = Message(
        sender="lead",
        recipient="worker-a",
        kind="task_assigned",
        content={"task_id": "t-1"},
    )

    mailbox.send(message)

    assert mailbox.pending("worker-a") == 1
    assert mailbox.receive("worker-a") == message
    assert mailbox.pending("worker-a") == 0


def test_mailbox_drain_returns_all_messages_in_order():
    mailbox = Mailbox()
    mailbox.send(Message(sender="lead", recipient="worker-a", kind="one"))
    mailbox.send(Message(sender="lead", recipient="worker-a", kind="two"))

    drained = mailbox.drain("worker-a")

    assert [message.kind for message in drained] == ["one", "two"]
    assert mailbox.pending("worker-a") == 0
