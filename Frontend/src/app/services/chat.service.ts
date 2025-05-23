// src/app/services/chat.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

interface ChatResponse {
  response: string;
  tokens: number;
}

@Injectable({
  providedIn: 'root',
})
export class ChatService {
  private apiUrl = 'https://gen-ai-qk66.onrender.com/ask';

  constructor(private http: HttpClient) {}

  sendPrompt(prompt: string): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(this.apiUrl, { prompt });
  }
}
