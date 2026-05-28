import axios from 'axios';

const BASE_URL = 'http://127.0.0.1:8000';

export const login = async (username, password) => {
  const response = await axios.post(`${BASE_URL}/api/token/`, {
    username,
    password
  });
  localStorage.setItem('access_token', response.data.access);
  localStorage.setItem('refresh_token', response.data.refresh);
  return response.data;
};

export const sendMessage = async (message) => {
  const token = localStorage.getItem('access_token');
  const response = await axios.post(
    `${BASE_URL}/api/chat/`,
    { message },
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  return response.data;
};

export const resetChat = async () => {
  const token = localStorage.getItem('access_token');
  await axios.post(
    `${BASE_URL}/api/reset/`,
    {},
    {
      headers: {
        Authorization: `Bearer ${token}`
      }
    }
  );
};