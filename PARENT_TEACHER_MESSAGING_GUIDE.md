# Parent–Teacher Messaging Implementation Guide

## Purpose and scope

Messaging is limited to Parent and Teacher accounts. It is designed for short,
learner-related communication and does not attempt to copy every social chat
feature. The first version supports text messages only—no files, group chats,
calls, reactions, or Student messaging.

The system permits a conversation only when:

1. The Parent has an approved connection to the Student.
2. The Student has an approved enrollment in the Teacher's active class.

## Database changes

The models are in `classroom/models.py`.

```python
class ParentTeacherConversation(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "student", "parent"],
                name="unique_parent_teacher_conversation",
            )
        ]


class ParentTeacherMessage(models.Model):
    conversation = models.ForeignKey(
        ParentTeacherConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
```

The migration is:

```text
classroom/migrations/0017_parentteacherconversation_parentteachermessage_and_more.py
```

It has already been applied to the local database.

## Backend code

```text
classroom/messaging_views.py
classroom/message_queries.py
classroom/context_processors.py
```

- `message_queries.py` applies the approved-link and approved-enrollment rules.
- `messaging_views.py` provides the inbox, conversation, desktop panel, start,
  and send endpoints.
- `context_processors.py` supplies the header panel and unread count on every
  Parent and Teacher Classroom page.

The context processor was registered in `DepedLMS/settings.py`:

```python
'classroom.context_processors.message_data',
```

## URL routes

The following names were added to `classroom/urls.py`:

```text
message_inbox
message_conversation_start
message_conversation
message_panel_conversation
message_send
```

## Interface code

```text
classroom/templates/classroom/messages/inbox.html
classroom/templates/classroom/messages/conversation.html
classroom/templates/classroom/messages/_panel_chat.html
classroom/static/classroom/css/messages.css
classroom/static/classroom/js/messages.js
```

`classroom/templates/classroom/master.html` now contains:

- A desktop message icon and floating panel for Parent and Teacher roles.
- A role-based fifth **Messages** item in the mobile bottom navigation.
- No message icon or navigation item for Students.

## User workflow

### Parent

1. Open **Messages**.
2. Select a Teacher connected to an approved learner and enrolled class.
3. The system creates or opens the unique conversation.
4. Send a text message about the displayed learner and class.

### Teacher

1. Open the desktop message panel or the mobile **Messages** tab.
2. Conversations identify the Parent, learner, subject, and class.
3. Open the conversation and reply.

Opening a conversation marks incoming messages as read. Unread messages appear
as a badge on the desktop icon and mobile navigation item.

## Desktop and mobile behavior

- Desktop: the top message icon opens a floating panel without leaving the
  current page. Selecting a conversation loads the chat inside that panel.
- Mobile/tablet: the top icon is hidden and the permanent bottom **Messages**
  tab opens a full-screen inbox and conversation screen.

## Commands for another computer

After pulling the repository on another computer, run:

```powershell
python manage.py migrate
python manage.py check
python manage.py runserver
```

No extra Python or JavaScript package is required.
