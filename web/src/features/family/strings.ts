/** Family-facing interface text in Gujarati, Hindi and English (spoken register, no jargon). */
import type { Language } from '@/api/types';

export const LANGUAGE_NAMES: Record<Language, string> = {
  gu: 'ગુજરાતી',
  hi: 'हिन्दी',
  en: 'English',
};

export interface FamilyStrings {
  title: string;
  listen: string;
  pause: string;
  speed: string;
  noAudio: string;
  figures: Record<'billed' | 'payable' | 'at_risk' | 'recoverable', string>;
  whatHappened: string;
  why: string;
  nextSteps: string;
  appealTitle: string;
  appealStatus: Record<'draft' | 'in_review' | 'signed' | 'exported', string>;
  desk: string;
  privacy: (expires: string) => string;
  disclaimer: string;
  invalidTitle: string;
  invalidBody: string;
  checking: string;
  checkingBody: string;
  writing: string;
  draftTitle: string;
  draftBody: string;
  draftButton: string;
  signTitle: string;
  signName: string;
  signDeclaration: string;
  signButton: string;
  download: string;
  signedBy: (name: string) => string;
  appealEnglishNote: string;
  stepDone: string;
  language: string;
}

export const STRINGS: Record<Language, FamilyStrings> = {
  en: {
    title: 'Your hospital claim, explained',
    listen: 'Listen',
    pause: 'Pause',
    speed: 'Speed',
    noAudio: 'Audio is not ready for this language yet.',
    figures: {
      billed: 'Hospital bill',
      payable: 'Insurance should pay',
      at_risk: 'May not be paid',
      recoverable: 'Can be claimed back',
    },
    whatHappened: 'What happened',
    why: 'Why',
    nextSteps: 'What to do next',
    appealTitle: 'Appeal to the insurer',
    appealStatus: {
      draft: 'The hospital is preparing an appeal.',
      in_review: 'The appeal is being checked at the hospital.',
      signed: 'The appeal has been checked and signed.',
      exported: 'The signed appeal is ready to send to the insurer.',
    },
    desk: 'Questions? Visit the hospital desk',
    privacy: (expires) =>
      `This page shows no names or ID numbers. The link stops working on ${expires}.`,
    disclaimer: 'Arzi is decision support. A qualified person reviews and signs every appeal.',
    invalidTitle: 'This link has expired',
    invalidBody: 'Ask the hospital desk for a new link.',
    checking: 'Checking your documents',
    checkingBody:
      'Arzi is reading every page and checking it against the rules. This takes about a minute.',
    writing: 'Writing the explanation in Gujarati, Hindi and English…',
    draftTitle: 'Challenge the decision',
    draftBody:
      'Arzi can draft a letter to the insurer’s complaints officer, citing the rules it found. You read it, sign it with your name, and send it.',
    draftButton: 'Draft my appeal letter',
    signTitle: 'Read, then sign',
    signName: 'Your full name',
    signDeclaration: 'I have read this letter and it is correct to the best of my knowledge.',
    signButton: 'Sign the letter',
    download: 'Download the signed letter (PDF)',
    signedBy: (name) => `Signed by ${name}`,
    appealEnglishNote: 'The letter is in English, as insurers expect.',
    stepDone: 'Done',
    language: 'Language',
  },
  hi: {
    title: 'आपके अस्पताल के क्लेम की आसान जानकारी',
    listen: 'सुनिए',
    pause: 'रोकिए',
    speed: 'गति',
    noAudio: 'इस भाषा में आवाज़ अभी तैयार नहीं है।',
    figures: {
      billed: 'अस्पताल का बिल',
      payable: 'बीमा से मिलना चाहिए',
      at_risk: 'शायद न मिले',
      recoverable: 'वापस माँगा जा सकता है',
    },
    whatHappened: 'क्या हुआ',
    why: 'क्यों',
    nextSteps: 'अब क्या करें',
    appealTitle: 'बीमा कंपनी से अपील',
    appealStatus: {
      draft: 'अस्पताल अपील तैयार कर रहा है।',
      in_review: 'अस्पताल में अपील की जाँच हो रही है।',
      signed: 'अपील की जाँच हो गई है और उस पर हस्ताक्षर हो गए हैं।',
      exported: 'हस्ताक्षर की हुई अपील बीमा कंपनी को भेजने के लिए तैयार है।',
    },
    desk: 'कोई सवाल? अस्पताल डेस्क पर आइए',
    privacy: (expires) => `इस पेज पर कोई नाम या आईडी नंबर नहीं है। यह लिंक ${expires} को बंद हो जाएगा।`,
    disclaimer: 'Arzi निर्णय में मदद करता है। हर अपील की जाँच और हस्ताक्षर एक योग्य व्यक्ति करता है।',
    invalidTitle: 'यह लिंक अब काम नहीं करता',
    invalidBody: 'नए लिंक के लिए अस्पताल डेस्क से पूछिए।',
    checking: 'आपके कागज़ जाँचे जा रहे हैं',
    checkingBody: 'Arzi हर पन्ना पढ़कर नियमों से मिला रहा है। इसमें लगभग एक मिनट लगता है।',
    writing: 'गुजराती, हिन्दी और अंग्रेज़ी में जानकारी लिखी जा रही है…',
    draftTitle: 'फ़ैसले को चुनौती दीजिए',
    draftBody:
      'Arzi बीमा कंपनी के शिकायत अधिकारी के लिए नियमों के साथ एक पत्र तैयार कर सकता है। आप उसे पढ़कर, अपने नाम से हस्ताक्षर करके भेजिए।',
    draftButton: 'मेरा अपील पत्र तैयार कीजिए',
    signTitle: 'पढ़िए, फिर हस्ताक्षर कीजिए',
    signName: 'आपका पूरा नाम',
    signDeclaration: 'मैंने यह पत्र पढ़ लिया है और मेरी जानकारी के अनुसार यह सही है।',
    signButton: 'पत्र पर हस्ताक्षर कीजिए',
    download: 'हस्ताक्षर किया हुआ पत्र डाउनलोड कीजिए (PDF)',
    signedBy: (name) => `${name} द्वारा हस्ताक्षरित`,
    appealEnglishNote: 'पत्र अंग्रेज़ी में है, जैसा बीमा कंपनियाँ चाहती हैं।',
    stepDone: 'हो गया',
    language: 'भाषा',
  },
  gu: {
    title: 'તમારા હોસ્પિટલના ક્લેમની સરળ સમજ',
    listen: 'સાંભળો',
    pause: 'રોકો',
    speed: 'ઝડપ',
    noAudio: 'આ ભાષામાં અવાજ હજી તૈયાર નથી.',
    figures: {
      billed: 'હોસ્પિટલનું બિલ',
      payable: 'વીમામાંથી મળવા જોઈએ',
      at_risk: 'કદાચ ન મળે',
      recoverable: 'પાછા માગી શકાય',
    },
    whatHappened: 'શું થયું',
    why: 'કેમ',
    nextSteps: 'હવે શું કરવું',
    appealTitle: 'વીમા કંપનીને અપીલ',
    appealStatus: {
      draft: 'હોસ્પિટલ અપીલ તૈયાર કરી રહી છે.',
      in_review: 'હોસ્પિટલમાં અપીલ તપાસાઈ રહી છે.',
      signed: 'અપીલ તપાસાઈ ગઈ છે અને તેના પર સહી થઈ ગઈ છે.',
      exported: 'સહી કરેલી અપીલ વીમા કંપનીને મોકલવા તૈયાર છે.',
    },
    desk: 'કોઈ પ્રશ્ન? હોસ્પિટલના ડેસ્ક પર આવો',
    privacy: (expires) => `આ પાના પર કોઈ નામ કે આઈડી નંબર નથી. આ લિંક ${expires} ના રોજ બંધ થઈ જશે.`,
    disclaimer: 'Arzi નિર્ણયમાં મદદ કરે છે. દરેક અપીલ એક જાણકાર વ્યક્તિ તપાસીને સહી કરે છે.',
    invalidTitle: 'આ લિંક હવે ચાલતી નથી',
    invalidBody: 'નવી લિંક માટે હોસ્પિટલના ડેસ્ક પર પૂછો.',
    checking: 'તમારા કાગળો તપાસાઈ રહ્યા છે',
    checkingBody: 'Arzi દરેક પાનું વાંચીને નિયમો સાથે સરખાવે છે. આમાં લગભગ એક મિનિટ લાગે છે.',
    writing: 'ગુજરાતી, હિન્દી અને અંગ્રેજીમાં સમજૂતી લખાઈ રહી છે…',
    draftTitle: 'નિર્ણયને પડકારો',
    draftBody:
      'Arzi વીમા કંપનીના ફરિયાદ અધિકારી માટે નિયમો સાથે એક પત્ર તૈયાર કરી શકે છે. તમે તે વાંચીને, તમારા નામથી સહી કરીને મોકલો.',
    draftButton: 'મારો અપીલ પત્ર તૈયાર કરો',
    signTitle: 'વાંચો, પછી સહી કરો',
    signName: 'તમારું પૂરું નામ',
    signDeclaration: 'મેં આ પત્ર વાંચ્યો છે અને મારી જાણ મુજબ તે સાચો છે.',
    signButton: 'પત્ર પર સહી કરો',
    download: 'સહી કરેલો પત્ર ડાઉનલોડ કરો (PDF)',
    signedBy: (name) => `${name} દ્વારા સહી કરેલ`,
    appealEnglishNote: 'પત્ર અંગ્રેજીમાં છે, જેમ વીમા કંપનીઓ ઇચ્છે છે.',
    stepDone: 'થઈ ગયું',
    language: 'ભાષા',
  },
};

export function initialLanguage(): Language {
  try {
    const saved = window.localStorage.getItem('arzi.family.lang');
    if (saved === 'gu' || saved === 'hi' || saved === 'en') return saved;
  } catch {
    // Storage blocked: fall through to the browser's language.
  }
  const browser = navigator.language.slice(0, 2);
  return browser === 'hi' || browser === 'en' ? browser : 'gu';
}

export function rememberLanguage(lang: Language): void {
  try {
    window.localStorage.setItem('arzi.family.lang', lang);
  } catch {
    // Not remembered; the choice still applies on this page.
  }
}

export function formatDateIn(lang: Language, iso: string): string {
  const locale = lang === 'en' ? 'en-IN' : `${lang}-IN`;
  return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric' }).format(
    new Date(iso),
  );
}

export interface CheckStrings {
  title: string;
  intro: string;
  decision: string;
  rejected: string;
  partlyPaid: string;
  letter: string;
  policy: string;
  bill: string;
  discharge: string;
  optional: string;
  choose: string;
  consent: string;
  submit: string;
  privacy: string;
  free: string;
}

export const CHECK_STRINGS: Record<Language, CheckStrings> = {
  en: {
    title: 'Was your health insurance claim rejected or cut?',
    intro:
      'Upload the insurer’s letter, your policy and the hospital bill. Arzi checks them against IRDAI rules and your policy, explains what it finds in your language, and can draft an appeal for you to sign.',
    decision: 'What did the insurer decide?',
    rejected: 'Rejected the claim',
    partlyPaid: 'Paid only part of it',
    letter: 'Insurer’s letter',
    policy: 'Policy schedule or wording',
    bill: 'Final hospital bill',
    discharge: 'Discharge summary',
    optional: 'optional',
    choose: 'Choose file',
    consent:
      'I agree that Arzi may read these documents to check this claim. Names and ID numbers are removed before any AI reads them, and everything is deleted after 7 days.',
    submit: 'Check my claim',
    privacy: 'Free. No account needed. Synthetic documents only during this demo.',
    free: 'Free check',
  },
  hi: {
    title: 'क्या आपका स्वास्थ्य बीमा क्लेम रद्द हुआ या कम मिला?',
    intro:
      'बीमा कंपनी का पत्र, अपनी पॉलिसी और अस्पताल का बिल अपलोड कीजिए। Arzi इन्हें IRDAI के नियमों और आपकी पॉलिसी से मिलाता है, आपकी भाषा में समझाता है, और आपके हस्ताक्षर के लिए अपील तैयार कर सकता है।',
    decision: 'बीमा कंपनी ने क्या फ़ैसला किया?',
    rejected: 'क्लेम रद्द कर दिया',
    partlyPaid: 'सिर्फ़ कुछ हिस्सा दिया',
    letter: 'बीमा कंपनी का पत्र',
    policy: 'पॉलिसी शेड्यूल या शर्तें',
    bill: 'अस्पताल का अंतिम बिल',
    discharge: 'डिस्चार्ज समरी',
    optional: 'वैकल्पिक',
    choose: 'फ़ाइल चुनिए',
    consent:
      'मैं सहमत हूँ कि Arzi इस क्लेम की जाँच के लिए ये कागज़ पढ़ सकता है। AI के पढ़ने से पहले नाम और आईडी नंबर हटा दिए जाते हैं, और 7 दिन बाद सब मिटा दिया जाता है।',
    submit: 'मेरा क्लेम जाँचिए',
    privacy: 'मुफ़्त। कोई खाता नहीं चाहिए। इस डेमो में सिर्फ़ नमूना कागज़।',
    free: 'मुफ़्त जाँच',
  },
  gu: {
    title: 'શું તમારો આરોગ્ય વીમાનો ક્લેમ નકાર્યો કે ઓછો આપ્યો?',
    intro:
      'વીમા કંપનીનો પત્ર, તમારી પોલિસી અને હોસ્પિટલનું બિલ અપલોડ કરો. Arzi તેને IRDAI ના નિયમો અને તમારી પોલિસી સાથે સરખાવે છે, તમારી ભાષામાં સમજાવે છે, અને તમારી સહી માટે અપીલ તૈયાર કરી શકે છે.',
    decision: 'વીમા કંપનીએ શું નિર્ણય લીધો?',
    rejected: 'ક્લેમ નકાર્યો',
    partlyPaid: 'ફક્ત થોડો ભાગ આપ્યો',
    letter: 'વીમા કંપનીનો પત્ર',
    policy: 'પોલિસી શેડ્યુલ અથવા શરતો',
    bill: 'હોસ્પિટલનું અંતિમ બિલ',
    discharge: 'ડિસ્ચાર્જ સમરી',
    optional: 'વૈકલ્પિક',
    choose: 'ફાઇલ પસંદ કરો',
    consent:
      'હું સંમત છું કે Arzi આ ક્લેમની તપાસ માટે આ કાગળો વાંચી શકે. AI વાંચે તે પહેલાં નામ અને આઈડી નંબર કાઢી નખાય છે, અને 7 દિવસ પછી બધું ભૂંસી નખાય છે.',
    submit: 'મારો ક્લેમ તપાસો',
    privacy: 'મફત. કોઈ ખાતાની જરૂર નથી. આ ડેમોમાં ફક્ત નમૂનાના કાગળો.',
    free: 'મફત તપાસ',
  },
};
