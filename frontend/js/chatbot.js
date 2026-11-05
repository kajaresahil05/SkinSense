/**
 * SkinSense — AI Assistant Chatbot Module v2.0
 * Fixes:
 *  - Uses correct IDs: chat-text-input, chat-send-btn, chat-messages
 *  - No form wrapper — binds click and Enter key directly
 *  - Sends to /api/chat (standard endpoint)
 *  - Proper typing indicator with role-consistent styling
 *  - Image attachment support
 */

let _chatConversationId = 'session-' + Math.random().toString(36).substring(2, 9);
let _chatImageFile      = null;
let _isListening        = false;
let _ttsEnabled         = false;
let _recognition        = null;

document.addEventListener('DOMContentLoaded', () => {
  ChatModule.init();
});

window.ChatModule = {
  init: function () {
    window.SectionHooks['assistant'] = () => {
      this._focusInput();
      this.loadLatestScanContext();
    };
    this._bindEvents();
  },

  _getSpeechLocale: function (langCode) {
    const mapping = {
      'hi': 'hi-IN',
      'bho': 'hi-IN',
      'mr': 'mr-IN',
      'bn': 'bn-IN',
      'ta': 'ta-IN',
      'te': 'te-IN',
      'gu': 'gu-IN',
      'kn': 'kn-IN',
      'es': 'es-ES',
      'en': 'en-US'
    };
    return mapping[langCode] || 'en-US';
  },

  _bindEvents: function () {
    const input      = document.getElementById('chat-text-input');
    const sendBtn    = document.getElementById('chat-send-btn');
    const attachBtn  = document.getElementById('chat-attach-btn');
    const voiceBtn   = document.getElementById('chat-voice-btn');
    const ttsBtn     = document.getElementById('chat-tts-toggle');
    const imgInput   = document.getElementById('chat-image-input');
    const removeAtt  = document.getElementById('chat-remove-attach');
    const clearBtn   = document.getElementById('clear-chat-btn');

    if (sendBtn) {
      sendBtn.addEventListener('click', () => this._handleSend());
    }

    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this._handleSend();
        }
      });
    }

    if (attachBtn && imgInput) {
      attachBtn.addEventListener('click', () => imgInput.click());
    }

    if (voiceBtn) {
      voiceBtn.addEventListener('click', () => this._toggleVoiceInput());
    }

    if (ttsBtn) {
      ttsBtn.addEventListener('click', () => this._toggleTts());
    }

    if (imgInput) {
      imgInput.addEventListener('change', (e) => {
        _chatImageFile = e.target.files?.[0] || null;
        const prevBox = document.getElementById('chat-attach-preview');
        const nameEl  = document.getElementById('chat-attach-filename');
        if (_chatImageFile && prevBox && nameEl) {
          nameEl.innerHTML = `<i class="fa-solid fa-paperclip me-1"></i>Attached: ${this._truncate(_chatImageFile.name, 20)}`;
          prevBox.classList.remove('d-none');
          prevBox.classList.add('d-flex');
        }
      });
    }

    if (removeAtt) {
      removeAtt.addEventListener('click', () => {
        _chatImageFile = null;
        if (imgInput) imgInput.value = '';
        const prevBox = document.getElementById('chat-attach-preview');
        if (prevBox) {
          prevBox.classList.add('d-none');
          prevBox.classList.remove('d-flex');
        }
      });
    }

    const chatLangSelect = document.getElementById('chat-language');
    if (chatLangSelect) {
      chatLangSelect.value = (window.I18nModule ? window.I18nModule.currentLang : 'en');
      chatLangSelect.addEventListener('change', (e) => {
        if (window.I18nModule) {
          window.I18nModule.setLanguage(e.target.value);
        }
      });
    }

    window.addEventListener('languageChanged', (e) => {
      const newLang = e.detail?.lang || (window.I18nModule ? window.I18nModule.currentLang : 'en');
      if (chatLangSelect && chatLangSelect.value !== newLang) {
        chatLangSelect.value = newLang;
      }
      this.translateCurrentConversation(newLang);
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        const container = document.getElementById('chat-messages');
        const welcomeHtml = (window.I18nModule && window.I18nModule.t) ? window.I18nModule.t('chatWelcomeBubble') : '<strong>Hello! I\'m your SkinSense AI Assistant.</strong><br>I can help you understand your skin assessment results, explain common skin conditions, and provide general skin care guidance. How can I help you today?';
        if (container) {
          container.innerHTML = `
            <div class="d-flex gap-2 align-items-start">
              <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--teal-500),var(--teal-700));display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <i class="fa-solid fa-user-doctor text-white" style="font-size:0.8rem;"></i>
              </div>
              <div class="chat-bubble-assistant" data-i18n-html="chatWelcomeBubble">
                ${welcomeHtml}
              </div>
            </div>`;
        }
        const qp = document.getElementById('chat-quick-prompts');
        if (qp) qp.style.display = 'flex';
        _chatConversationId = 'session-' + Math.random().toString(36).substring(2, 9);
      });
    }
  },

  _toggleVoiceInput: function () {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      if (window.Toast) {
        window.Toast.show(
          'Voice recognition is not supported by your browser. Please use Google Chrome, Microsoft Edge, or Safari.',
          'warning',
          'Voice Input Unavailable'
        );
      }
      return;
    }

    if (_isListening) {
      this._stopVoiceInput();
      return;
    }

    try {
      _recognition = new SpeechRecognition();
      const currentLang = window.I18nModule ? window.I18nModule.currentLang : 'en';
      _recognition.lang = this._getSpeechLocale(currentLang);
      _recognition.interimResults = true;
      _recognition.continuous = false;

      const input = document.getElementById('chat-text-input');
      const statusBox = document.getElementById('chat-voice-status');
      const voiceIcon = document.getElementById('chat-voice-icon');

      _recognition.onstart = () => {
        _isListening = true;
        if (statusBox) statusBox.classList.replace('d-none', 'd-flex');
        if (voiceIcon) voiceIcon.className = 'fa-solid fa-microphone text-danger fa-beat';
      };

      _recognition.onresult = (e) => {
        let transcript = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
          transcript += e.results[i][0].transcript;
        }
        if (input) input.value = transcript;
      };

      _recognition.onerror = (e) => {
        console.warn('[VoiceInput] Speech recognition error:', e.error);
        this._stopVoiceInput();
        if (e.error === 'not-allowed' && window.Toast) {
          window.Toast.show('Microphone access was denied in browser settings.', 'error', 'Microphone Error');
        }
      };

      _recognition.onend = () => {
        this._stopVoiceInput();
      };

      _recognition.start();
    } catch (err) {
      console.error('[VoiceInput] Failed starting speech recognition:', err);
      this._stopVoiceInput();
    }
  },

  _stopVoiceInput: function () {
    _isListening = false;
    if (_recognition) {
      try { _recognition.stop(); } catch (e) {}
      _recognition = null;
    }
    const statusBox = document.getElementById('chat-voice-status');
    const voiceIcon = document.getElementById('chat-voice-icon');
    if (statusBox) statusBox.classList.replace('d-flex', 'd-none');
    if (voiceIcon) voiceIcon.className = 'fa-solid fa-microphone text-teal';
  },

  _toggleTts: function () {
    _ttsEnabled = !_ttsEnabled;
    const ttsIcon = document.getElementById('chat-tts-icon');
    const ttsBtn  = document.getElementById('chat-tts-toggle');

    if (_ttsEnabled) {
      if (ttsIcon) ttsIcon.className = 'fa-solid fa-volume-high text-teal';
      if (ttsBtn) ttsBtn.title = 'AI Voice Output Active (Click to Mute)';
      if (window.Toast) window.Toast.show('AI Voice Output Enabled', 'info', 'Read Aloud Active');
    } else {
      if (ttsIcon) ttsIcon.className = 'fa-solid fa-volume-xmark';
      if (ttsBtn) ttsBtn.title = 'Toggle AI Voice Output (Read Aloud)';
      if (window.speechSynthesis) window.speechSynthesis.cancel();
    }
  },

  _speakText: function (text) {
    if (!_ttsEnabled || !window.speechSynthesis) return;

    window.speechSynthesis.cancel();

    const cleanText = text
      .replace(/<[^>]*>/g, '')
      .replace(/###/g, '')
      .replace(/\*\*/g, '')
      .replace(/•/g, '')
      .trim();

    if (!cleanText) return;

    const currentLang = window.I18nModule ? window.I18nModule.currentLang : 'en';
    const utterance   = new SpeechSynthesisUtterance(cleanText);
    utterance.lang    = this._getSpeechLocale(currentLang);
    utterance.rate    = 1.0;
    utterance.pitch   = 1.0;

    window.speechSynthesis.speak(utterance);
  },

  loadLatestScanContext: async function () {
    const container = document.getElementById('assistant-last-scan-info');
    if (!container) return;
    const currentLang = (window.I18nModule && window.I18nModule.currentLang) ? window.I18nModule.currentLang : 'en';
    const matchLabel  = (window.I18nModule && window.I18nModule.t) ? window.I18nModule.t('match') : 'match';
    const askAiLabel  = (window.I18nModule && window.I18nModule.t) ? window.I18nModule.t('ask_ai') : 'Discuss this scan';
    try {
      const res  = await fetch('/api/history?limit=1');
      const data = await res.json();
      if (data.status === 'success' && data.assessments && data.assessments.length > 0) {
        const scan    = data.assessments[0];
        const score   = ((scan.model_score || 0) * 100).toFixed(1);
        const dateStr = scan.created_at ? new Date(scan.created_at).toLocaleDateString(this._getSpeechLocale(currentLang), { month: 'short', day: 'numeric' }) : '';
        const sevClass = scan.severity_category === 'High' ? 'text-rose fw-700' : 'text-teal fw-600';
        container.innerHTML = `
          <div class="p-3 rounded-3 bg-teal-soft border border-teal mb-2">
            <div class="fw-700 text-truncate mb-1" style="color:var(--teal-700);">${scan.predicted_name || 'Scan Result'}</div>
            <div class="d-flex justify-content-between align-items-center mb-1">
              <span class="badge-pill badge-teal" style="font-size:0.7rem;">${score}% ${matchLabel}</span>
              <span class="${sevClass}" style="font-size:0.75rem;">${scan.severity_category || 'Mild'}</span>
            </div>
            <div class="text-muted" style="font-size:0.7rem;">Date: ${dateStr} · ID: ${scan.id}</div>
          </div>
          <button class="btn btn-ghost btn-sm w-100 p-1 text-teal" onclick="sendChatMessage('${askAiLabel} ${scan.id}')" style="font-size:0.75rem;">
            <i class="fa-solid fa-comments me-1"></i>${askAiLabel}
          </button>`;
      } else {
        const noScanText = (window.I18nModule && window.I18nModule.t) ? window.I18nModule.t('no_scans_yet') : 'No recent scan recorded.';
        container.innerHTML = `<div class="text-muted small">${noScanText}</div>`;
      }
    } catch (e) {
      container.innerHTML = '<div class="text-muted small">No recent scan context.</div>';
    }
  },

  translateCurrentConversation: async function (targetLang) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    // 1. Update Welcome bubble if present
    const welcomeBubbles = container.querySelectorAll('[data-i18n-html="chatWelcomeBubble"]');
    welcomeBubbles.forEach(el => {
      if (window.I18nModule && window.I18nModule.t) {
        el.innerHTML = window.I18nModule.t('chatWelcomeBubble');
      }
    });

    // 2. Refresh active scan context sidebar with target language
    this.loadLatestScanContext();

    // 3. Translate all assistant message turns
    const assistantBubbles = container.querySelectorAll('.chat-bubble-assistant');
    for (const bubble of assistantBubbles) {
      if (bubble.hasAttribute('data-i18n-html')) continue;

      let rawText = bubble.getAttribute('data-original-text');
      if (!rawText) {
        rawText = bubble.innerText || bubble.textContent;
        bubble.setAttribute('data-original-text', rawText);
      }

      if (!rawText || !rawText.trim()) continue;

      try {
        const res = await fetch('/api/chat/translate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: rawText, target_lang: targetLang })
        });
        const data = await res.json();
        if (data.status === 'success' && data.translated_text) {
          let html = data.translated_text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

          html = html.replace(/### (.*?)(?:\n|$)/g, '<h6 class="fw-700 mt-2 mb-1" style="color:var(--teal-600);">$1</h6>');
          html = html.replace(/## (.*?)(?:\n|$)/g, '<h6 class="fw-700 mt-2 mb-1">$1</h6>');
          html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
          html = html.replace(/^\- (.*?)$/gm, '• $1');
          html = html.replace(/\n/g, '<br>');

          bubble.innerHTML = html;
        }
      } catch (err) {
        console.warn('[ChatModule] Conversation translation error:', err);
      }
    }
  },

  _handleSend: function () {
    const input = document.getElementById('chat-text-input');
    const text  = input?.value.trim();
    if (!text && !_chatImageFile) return;
    if (_chatImageFile && !document.getElementById('chat-screening-consent')?.checked) {
      Toast.warning('Please allow the skin-photo suitability check before sending an image.');
      return;
    }

    if (text) {
      this._appendMessage('user', text);
      if (input) input.value = '';
    }

    const imageToSend = _chatImageFile;
    _chatImageFile    = null;
    const imgInput    = document.getElementById('chat-image-input');
    if (imgInput) imgInput.value = '';

    this._sendToBackend(text, imageToSend);
  },

  _sendToBackend: async function (message, imageFile) {
    const typingId = this._showTyping();
    const sendBtn  = document.getElementById('chat-send-btn');
    if (sendBtn) sendBtn.disabled = true;

    const currentLang = (window.I18nModule && window.I18nModule.currentLang) ? window.I18nModule.currentLang : 'en';

    const controller = new AbortController();
    const timeoutId  = setTimeout(() => controller.abort(), 35000);

    try {
      let res;
      if (imageFile) {
        const fd = new FormData();
        fd.append('message', message || '');
        fd.append('image', imageFile);
        fd.append('image_screening_consent', String(document.getElementById('chat-screening-consent')?.checked === true));
        fd.append('conversation_id', _chatConversationId);
        fd.append('lang', currentLang);
        res = await fetch('/api/chat', {
          method: 'POST',
          body: fd,
          signal: controller.signal
        });
      } else {
        res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, conversation_id: _chatConversationId, lang: currentLang }),
          signal: controller.signal
        });
      }
      clearTimeout(timeoutId);

      this._removeTyping(typingId);

      if (!res.ok) {
        const errText = (window.I18nModule && window.I18nModule.t)
          ? window.I18nModule.t('chat_connection_error')
          : 'Server error while fetching response. Please try again.';
        this._appendMessage('assistant', errText, true);
        return;
      }

      const data = await res.json();

      if (data.status === 'success') {
        let reply = (data.response && typeof data.response === 'object' && data.response.content)
          ? data.response.content
          : (typeof data.response === 'string' ? data.response : (data.message || ''));

        if (!reply || !reply.trim()) {
          reply = (window.I18nModule && window.I18nModule.t)
            ? window.I18nModule.t('chat_empty_error')
            : 'I could not generate a response. Please rephrase or try again.';
          this._appendMessage('assistant', reply, true);
        } else {
          this._appendMessage('assistant', reply);
        }

        // Hide quick prompts after first real message
        const qp = document.getElementById('chat-quick-prompts');
        if (qp) qp.style.display = 'none';
      } else {
        const errMsg = data.message || ((window.I18nModule && window.I18nModule.t) ? window.I18nModule.t('chat_empty_error') : 'I had trouble processing your request. Please try again.');
        this._appendMessage('assistant', errMsg, true);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      this._removeTyping(typingId);
      const isTimeout = (err.name === 'AbortError');
      const msgKey    = isTimeout ? 'chat_timeout_error' : 'chat_connection_error';
      const fallbackMsg = isTimeout
        ? 'Request timed out. Please check your connection and try again.'
        : 'Connection error. Please check your internet and try again.';
      const errMsg = (window.I18nModule && window.I18nModule.t) ? window.I18nModule.t(msgKey) : fallbackMsg;
      this._appendMessage('assistant', errMsg, true);
    } finally {
      if (sendBtn) sendBtn.disabled = false;
      const input = document.getElementById('chat-text-input');
      if (input) input.focus();
    }
  },

  _appendMessage: function (role, text, isError) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    let contentStr = (typeof text === 'object' && text !== null) ? (text.content || JSON.stringify(text)) : String(text || '');

    // Guard against empty content rendering empty bubbles
    if (!contentStr || !contentStr.trim()) {
      if (role === 'assistant') {
        contentStr = (window.I18nModule && window.I18nModule.t)
          ? window.I18nModule.t('chat_empty_error')
          : 'I could not generate a response. Please rephrase or try again.';
        isError = true;
      } else {
        return; // Don't append empty user messages
      }
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'd-flex gap-2 align-items-start mb-3';

    if (role === 'assistant') {
      const avatar = document.createElement('div');
      avatar.style.cssText = 'width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--teal-500),var(--teal-700));display:flex;align-items:center;justify-content:center;flex-shrink:0;';
      avatar.innerHTML = '<i class="fa-solid fa-user-doctor text-white" style="font-size:0.8rem;"></i>';
      wrapper.appendChild(avatar);
    } else {
      wrapper.style.justifyContent = 'flex-end';
    }

    const bubble = document.createElement('div');
    bubble.className = role === 'user' ? 'chat-bubble-user' : 'chat-bubble-assistant';
    if (isError) bubble.style.borderLeft = '3px solid var(--rose-400)';

    if (role === 'assistant') {
      bubble.setAttribute('data-original-text', contentStr);
    }

    // Basic markdown formatting for assistant responses
    let html = contentStr
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Format markdown bold, headers, lists
    html = html.replace(/### (.*?)(?:\n|$)/g, '<h6 class="fw-700 mt-2 mb-1" style="color:var(--teal-600);">$1</h6>');
    html = html.replace(/## (.*?)(?:\n|$)/g, '<h6 class="fw-700 mt-2 mb-1">$1</h6>');
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/^\- (.*?)$/gm, '• $1');
    html = html.replace(/\n/g, '<br>');

    bubble.innerHTML = html;

    wrapper.appendChild(bubble);
    container.appendChild(wrapper);
    container.scrollTop = container.scrollHeight;

    if (role === 'assistant' && !isError) {
      this._speakText(contentStr);
    }
  },

  _showTyping: function () {
    const container = document.getElementById('chat-messages');
    if (!container) return null;

    const id      = 'typing-' + Date.now();
    const wrapper = document.createElement('div');
    wrapper.id    = id;
    wrapper.className = 'd-flex gap-2 align-items-start mb-3';
    const avatar  = document.createElement('div');
    avatar.style.cssText = 'width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--teal-500),var(--teal-700));display:flex;align-items:center;justify-content:center;flex-shrink:0;';
    avatar.innerHTML = '<i class="fa-solid fa-user-doctor text-white" style="font-size:0.8rem;"></i>';

    const thinkingText = (window.I18nModule && window.I18nModule.t) ? window.I18nModule.t('chat_thinking') : 'Thinking...';

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble-assistant d-flex align-items-center gap-2';
    bubble.innerHTML = `
      <span class="text-muted" style="font-size:0.85rem; font-style:italic;">${thinkingText}</span>
      <div class="typing-indicator-dots">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>
    `;
    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    container.appendChild(wrapper);
    container.scrollTop = container.scrollHeight;
    return id;
  },

  _removeTyping: function (id) {
    if (id) {
      const el = document.getElementById(id);
      if (el) el.remove();
    }
  },

  _focusInput: function () {
    setTimeout(() => {
      const input = document.getElementById('chat-text-input');
      if (input) input.focus();
    }, 100);
  },

  _truncate: function (str, n) {
    return (str && str.length > n) ? str.slice(0, n) + '…' : (str || '');
  }
};

// ── Global helper (used by quick-prompt chips) ──
window.sendChatMessage = function (text) {
  const input = document.getElementById('chat-text-input');
  if (input) {
    input.value = text;
    ChatModule._handleSend();
  }
};

// Back-compat alias (used by chatbot.js sendChatPrompt calls)
window.sendChatPrompt = window.sendChatMessage;
