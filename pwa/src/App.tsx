import {
  ConsoleTemplate,
  ThemeProvider,
} from '@pipecat-ai/voice-ui-kit'
import '@pipecat-ai/voice-ui-kit/styles.css'
import './index.css'

// Stable object references — defined outside the component so they never
// change between renders, preventing the transport from being re-created.
const CONNECT_PARAMS = {
  webrtcRequestParams: { endpoint: '/offer' },
}

const CLIENT_OPTIONS = {
  callbacks: {
    onTransportStateChanged: (state: string) => {
      console.debug('[VoiceClaw] transport state:', state)
    },
  },
}

function App() {
  return (
    <ThemeProvider>
      <ConsoleTemplate
        transportType="smallwebrtc"
        connectParams={CONNECT_PARAMS}
        clientOptions={CLIENT_OPTIONS}
        titleText="VoiceClaw"
        connectOnMount={false}
        noAutoInitDevices
        noUserAudio
        noUserVideo
        noScreenControl
        noTextInput
        noConversation={false}
        noMetrics
        noSessionInfo
        noStatusInfo
        noThemeSwitch
        noLogo
        onServerMessage={(msg) => {
          console.debug('[VoiceClaw] server message:', msg)
        }}
      />
    </ThemeProvider>
  )
}

export default App
