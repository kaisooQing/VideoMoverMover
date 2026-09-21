import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
})

export default api
