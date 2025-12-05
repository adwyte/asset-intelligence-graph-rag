import { useEffect, useRef, useState } from "react";

export function useSpeechRecognition() {
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");

  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      console.warn("SpeechRecognition not supported in this browser.");
      return;
    }

    const rec = new SpeechRecognition();
    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = false;

    rec.onstart = () => setListening(true);

    rec.onresult = (event: any) => {
      const text = event.results[0][0].transcript;
      setTranscript(text);
    };

    rec.onerror = (e: any) => {
      console.error("Speech recognition error:", e.error);
      setListening(false);
    };

    rec.onend = () => {
      setListening(false);
    };

    recognitionRef.current = rec;
  }, []);

  const start = () => {
    if (!recognitionRef.current) {
      alert("Speech recognition not supported.");
      return;
    }

    try {
      setTranscript("");
      recognitionRef.current.start();
    } catch (e) {
      console.error("Cannot start recognition:", e);
    }
  };

  return { listening, transcript, start };
}
