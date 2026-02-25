#Base image: Slim version of Python 3.14.3 (latest stable at this point)
FROM python:3.14.3-slim

#Prevent Python from writing .pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
#Prevent Python from buffering stdout/stderr (ensures logs show up immediatly)
ENV PYTHONUNBUFFERED 1

#Set working directory inside the container
WORKDIR /app

#Copy dependency definition first to leverage DOcker layer caching
COPY requirements.txt .

#Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

#Copy the remaining project files
COPY . .

# Default command to execute the bot
CMD ["python", "kokoloko.py"]
