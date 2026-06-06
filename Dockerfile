# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port that Streamlit runs on
EXPOSE 8501

# Define environment variable for Streamlit to run on all IPs
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Run the Streamlit application when the container launches
# You can choose to run either main.py or streamlit_app.py
# For the Streamlit app:
CMD ["streamlit", "run", "streamlit_app.py"]

# If you wanted to run the console app instead:
# CMD ["python", "main.py"]