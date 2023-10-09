import os
import random
import base64

import streamlit as st

from utils import (
    haystack_is_ready,
    get_ratls_output,
    query_streaming
)

with open("./images/bot.jpg", "rb") as f:
    image_data = f.read()
    base64_image = base64.b64encode(image_data).decode("utf-8")

bot_image = f'<img class="bot-img" src="data:image/jpg;base64,{base64_image}">'

DEFAULT_QUESTION_AT_STARTUP = os.getenv("DEFAULT_QUESTION_AT_STARTUP", "Hi, I'm Data Center Cluster Fleet Service Agent, how can I help you?")
DEFAULT_ANSWER_AT_STARTUP = os.getenv("DEFAULT_ANSWER_AT_STARTUP", "Hi")

def set_state_if_absent(key, value):
    if key not in st.session_state:
        st.session_state[key] = value

def clean_markdown(string):
    return string.replace("$", "\$").replace(":", "\:")

# Setting page title and header
st.set_page_config(page_title="RAG Chatbot demo", page_icon=":robot_face:")

#st.markdown("<h1 style='text-align: center; font-family: Intel Clear ; color: #0071c5;'>\
#                RAG - A totally harmless bot😬</h1>", unsafe_allow_html=True)

with open("style.css", "r") as f:
   st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# Initialise session state variables
set_state_if_absent("generated", [DEFAULT_QUESTION_AT_STARTUP])
set_state_if_absent("past", [DEFAULT_ANSWER_AT_STARTUP])
st.title("Build Trustworthy and Confidential LLM (RAG) Inference with Intel® TDX Shield")

st.sidebar.image("./images/Intel.png")
st.sidebar.markdown("<h1>Options</h1>", unsafe_allow_html=True)
prompt_name = st.sidebar.radio("Choose a prompt:", ("General", "Fleet"))
counter_placeholder = st.sidebar.empty()
#counter_placeholder.write(f"Total cost of this conversation: ${st.session_state['total_cost']:.5f}")
clear_button = st.sidebar.button("Restart Conversation", key="clear")

model_type = "llama2"

def generate_prompt(prompt_name):
    if prompt_name == "Fleet":
        PROMPT_TEXT = """Below is an instruction that describes a task, paired with an input that \
            provides further context. Write response that appropriately completes the request.

        ### Instruction:
        Suppose you are a professional computer engineer at Intel. Paraphrase the context as a detailed summary.

        ### Input:
        {join(documents)}

        ### Answer:"""
        custom_prompt = PROMPT_TEXT
    elif prompt_name == "General":
        PROMPT_TEXT = """Suppose you are a system debug agent at Intel, please answer the question. Question: {query}; Answer:"""
        #custom_prompt = create_prompt_template(NAME, PROMPT_TEXT, OUTPUT_PARSER)
        custom_prompt = PROMPT_TEXT
    else:
        PROMPT_TEXT = """Suppose you are a system debug agent at Intel, please answer the question. Question: {query}; Answer:"""
        #custom_prompt = create_prompt_template(NAME, PROMPT_TEXT, OUTPUT_PARSER)
        custom_prompt = PROMPT_TEXT
    return custom_prompt

custom_prompt = generate_prompt(prompt_name)

# reset everything
def reset_results(*args):
    st.session_state.generated = [DEFAULT_QUESTION_AT_STARTUP]
    st.session_state.past = [DEFAULT_ANSWER_AT_STARTUP]

if clear_button:
    reset_results()

def generate_response_stream(question, custom_prompt):
    results = query_streaming(question, model_type, custom_prompt)
    return results

def resp_iter(r):
    try:
        return r.iter_content()
    except Exception as e:
        return r

# Check the connection
with st.spinner("⌛️ &nbsp;&nbsp; Chatbot-RAG demo is starting..."):
    if not haystack_is_ready(model_type):
        st.error("🚫 &nbsp;&nbsp; Connection Error. Is the chatbot-rag pipeline service running?")
    else:
        st.success("✅ &nbsp;&nbsp; Secure connection established with Intel\u00AE TDX technology")

    status = get_ratls_output()
    if "grpc-ratls" in status:
        with st.expander('Connection Message:', expanded=True):
            st.text(status)

# container for chat history
response_container = st.container()
# container for text box
container = st.container()

prompt = [
        "Why is Intel pursuing a formalized advanced services offering for its Xeon-based processors?",
        "What are the specific capabilities that are included as part of advanced services for Intel® Xeon® Processors?",
        "With the introduction of advanced services, will my support level change?",
        "Are the services and capabilities included in advanced services exclusive to a particular CSP customer or will they be offered to other customers?",
        "What is the advanced services business model?",
        "Will new platforms be Added/ Removed to advanced services during a subscription period?",
        "Can new capabilities be added to the list if they are not on there?",
        "What is the SLA for production signed patch for debug? Does this have a bearing on issue resolution SLA?",
        "What is the SLA for delivery of fleet enhancement features? When is the credit used - at the time of request or at the time of delivery?",
        "Is fleet service scope be applicable for non-POR post TTM changes?",
        "If Intel has another major event, similar to that in 2018, will Intel provide servicing to the platform?",
        "Are credits applicable to advanced debug functions and fleet management software functions?",
        ]

placeholder = random.choice(prompt)

with container:
    with st.form(key='my_form', clear_on_submit=True):
        print("call container")
        user_input = st.text_area("You:", key='input', placeholder="Ask a random fleet question", height=100)
        submit_button = st.form_submit_button(label='Send')
        if submit_button:
            if user_input:
                results = generate_response_stream(user_input, custom_prompt)
                st.session_state['past'].append(user_input)
            else:
                results = generate_response_stream(placeholder, custom_prompt)
                st.session_state['past'].append(placeholder)
            st.session_state['generated'].append(results)

if st.session_state['generated']:
    with response_container:
        for i in range(len(st.session_state['generated'])):
            if i == 0:
                st.markdown(f"""
                            <div class="container">
                                {bot_image}
                                <p class='answer'> Hi, I'm Data Center Cluster Fleet Service Agent, how can I help you? </p>
                            </div>
                            """, 
                            unsafe_allow_html=True)
            else:
                user_input=st.session_state["past"][i]
                st.markdown(f"""
                            <div class="container-user">
                                <img class="user-img" src="https://api.dicebear.com/5.x/fun-emoji/svg?seed=88">
                                <p class='question'> {user_input} </p>
                            </div>
                            
                            """,
                            unsafe_allow_html=True)
                
                r = st.session_state["generated"][i]
                if isinstance(r, str):  
                    #message(st.session_state["generated"][i], key=str(i))
                    response = st.session_state["generated"][i]
                    st.markdown(f"""
                                    <div class="container">
                                        {bot_image}
                                        <p class='answer'> {response} </p>
                                    </div>
                                """,
                                unsafe_allow_html=True
                                )
                else:
                    report = []
                    with st.empty():
                        # Looping over the response
                        for resp in resp_iter(r):
                            # join method to concatenate the elements of the list 
                            # into a single string, 
                            # then strip out any empty strings
                            report.append(resp.decode('utf-8', 'ignore'))
                            result = "".join(report).strip()
                            st.markdown(f"""
                                        <div class="container">
                                           {bot_image}
                                            <p class='answer'> {result} </p>
                                        </div>
                                        """,
                                        unsafe_allow_html=True
                                    )
                        st.session_state["generated"][i] = result
