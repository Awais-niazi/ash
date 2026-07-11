import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL;

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

export const getHistory = async () => {
  const token = localStorage.getItem('access_token');
  const response = await axios.get(`${BASE_URL}/api/history/`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return response.data.messages || [];
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