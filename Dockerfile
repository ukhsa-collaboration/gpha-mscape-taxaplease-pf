FROM python:3.15.2

ADD . /app
WORKDIR /app
RUN pip install .

CMD ["taxaplease"]
