import React from 'react';
import { View } from 'react-native';
import FeedScreen from './src/screens/FeedScreen';

export default function App() {
    return (
        <View style={{ flex: 1 }}>
            <FeedScreen />
        </View>
    );
}
