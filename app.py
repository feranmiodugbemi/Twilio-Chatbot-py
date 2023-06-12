import telebot
from faunadb import query as q
from faunadb.objects import Ref
from faunadb.client import FaunaClient
import openai
from dotenv import load_dotenv
from twilio.rest import Client
import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)



chat_list = []

def prompt(username, question):
    # Create a FaunaDB client
    load_dotenv()
    client = FaunaClient(secret=os.getenv('FAUNA_SECRET_KEY'))
    data = {
        "username": username,
        "message": {
            "role": "user",
            "content": question
        }
    }
    result = client.query(
        q.create(
            q.collection("Messages"),
            {
            "data": data
            }
        )
    )
    index_name = "users_message_by_username"
    username = username
    # Paginate over all the documents in the collection using the index
    result = client.query(
        q.map_(
            lambda ref: q.get(ref),
            q.paginate(q.match(q.index(index_name), username))
        )
    )

    messages = []

    for document in result['data']:
        message = document['data']['message']
        messages.append(message)

    # Set up OpenAI API
    openai.api_key = os.getenv('OPENAI_API_KEY')

    # Define the assistant's persona in a system message
    system_message = {"role":"system", "content" : "You are a dietitian, food nutritionist, and fitness consultant, you provide expert guidance and advice to individuals facing dietary challenges or seeking direction on their food choices and exercise routines. You offer personalized recommendations and solutions to those who are unsure about the right foods to eat or the appropriate exercises to engage in. If user says hello or any greeting introduce yourself."}

    # Construct the conversation prompt with user messages and the system message
    prompt_with_persona = [system_message] + [
        {"role": "user", "content": message["content"]} if message["role"] == "user"
        else {"role": "assistant", "content": message["content"]} for message in messages
    ]

    # Generate a response from the model
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=prompt_with_persona
    )

    # Extract the generated reply from the API response
    generated_reply = response["choices"][0]["message"]["content"]
    
    newdata = {
        "username": username,
        "message": {
            "role": "assistant",
            "content": generated_reply
        }
    }
    result = client.query(
        q.create(
            q.collection("Messages"),
            {
            "data": newdata
            }
        )
    )

    return generated_reply


@app.route('/whatsapp', methods=["POST", "GET"])
def chat():
    load_dotenv()
    twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')
    sender_phone_number = request.values.get('From', '')
    username = request.values.get('ProfileName')
    question = request.values.get('Body')
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    Twilioclient = Client(account_sid, auth_token)
    client = FaunaClient(
        secret=os.getenv('FAUNA_SECRET_KEY')
    )
    reply = None
    user_exists = client.query(
        q.exists(q.match(q.index("users_message_by_username"), username)))
    if user_exists:
        reply = prompt(username, question)
        answer = Twilioclient.messages.create(
        body=reply,
        from_=twilio_phone_number,
        to=sender_phone_number
    )
    else:
        client.query(
            q.create(
                q.collection("Users"),
                {
                    "data": {
                        "username": username
                    }
                }   
            )
        )
        reply = prompt(username, question)
        answer = Twilioclient.messages.create(
        body=reply,
        from_=twilio_phone_number,
        to=sender_phone_number
    )
    return str(answer.sid)
        
        




if __name__ == '__main__':
    app.run(debug=True)